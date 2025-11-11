"""
长期记忆模块

本模块实现基于Qdrant的长期记忆功能，用于存储和检索交易经验。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from decimal import Decimal
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, Range
)
from openai import AsyncOpenAI

from src.core.logger import get_logger
from src.core.exceptions import TradingSystemError
from src.models.memory import TradingExperience, MemoryQuery


logger = get_logger(__name__)


class QdrantLongTermMemory:
    """基于Qdrant的长期记忆"""

    COLLECTION_NAME = "trading_experiences"
    VECTOR_SIZE = 1536  # OpenAI text-embedding-ada-002维度

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        openai_api_key: Optional[str] = None,
        embedding_model: str = "text-embedding-ada-002"
    ):
        """
        初始化Qdrant长期记忆

        Args:
            qdrant_url: Qdrant服务URL
            openai_api_key: OpenAI API密钥（用于embedding）
            embedding_model: 使用的embedding模型
        """
        self.qdrant_url = qdrant_url
        self.embedding_model = embedding_model
        self.qdrant: Optional[AsyncQdrantClient] = None
        self.openai: Optional[AsyncOpenAI] = None

        if openai_api_key:
            self.openai = AsyncOpenAI(api_key=openai_api_key)

        self.logger = logger

    async def initialize(self) -> None:
        """初始化Qdrant客户端和集合"""
        try:
            self.qdrant = AsyncQdrantClient(url=self.qdrant_url)

            # 检查集合是否存在
            collections = await self.qdrant.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.COLLECTION_NAME not in collection_names:
                # 创建集合
                await self.qdrant.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.VECTOR_SIZE,
                        distance=Distance.COSINE
                    )
                )
                self.logger.info(f"Created Qdrant collection: {self.COLLECTION_NAME}")
            else:
                self.logger.info(f"Qdrant collection already exists: {self.COLLECTION_NAME}")

        except Exception as e:
            raise TradingSystemError(
                message="Failed to initialize Qdrant",
                details={"qdrant_url": self.qdrant_url},
                original_exception=e
            )

    async def close(self) -> None:
        """关闭Qdrant连接"""
        if self.qdrant:
            await self.qdrant.close()
            self.logger.info("Closed Qdrant connection")

        if self.openai:
            await self.openai.close()

    async def _generate_embedding(self, text: str) -> List[float]:
        """
        生成文本的embedding向量

        Args:
            text: 输入文本

        Returns:
            embedding向量
        """
        if not self.openai:
            raise TradingSystemError(
                message="OpenAI client not initialized",
                details={"embedding_model": self.embedding_model},
                original_exception=None
            )

        try:
            response = await self.openai.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            raise TradingSystemError(
                message="Failed to generate embedding",
                details={"text_length": len(text)},
                original_exception=e
            )

    def _experience_to_payload(self, experience: TradingExperience) -> dict:
        """将TradingExperience转换为Qdrant payload"""
        return {
            "id": experience.id,
            "timestamp": experience.timestamp,
            "datetime": experience.dt.isoformat(),
            "situation": experience.situation,
            "decision": experience.decision,
            "decision_reasoning": experience.decision_reasoning,
            "outcome": experience.outcome,
            "pnl": float(experience.pnl),
            "pnl_percentage": float(experience.pnl_percentage),
            "reflection": experience.reflection,
            "lessons_learned": experience.lessons_learned,
            "tags": experience.tags,
            "importance_score": experience.importance_score
        }

    def _payload_to_experience(self, payload: dict) -> TradingExperience:
        """将Qdrant payload转换为TradingExperience"""
        return TradingExperience(
            id=payload["id"],
            timestamp=payload["timestamp"],
            dt=datetime.fromisoformat(payload["datetime"]),
            situation=payload["situation"],
            situation_embedding=None,  # 不需要返回embedding
            decision=payload["decision"],
            decision_reasoning=payload["decision_reasoning"],
            outcome=payload["outcome"],
            pnl=Decimal(str(payload["pnl"])),
            pnl_percentage=Decimal(str(payload["pnl_percentage"])),
            reflection=payload.get("reflection"),
            lessons_learned=payload.get("lessons_learned", []),
            tags=payload.get("tags", []),
            importance_score=payload.get("importance_score", 0.0)
        )

    async def store_experience(
        self,
        experience: TradingExperience
    ) -> str:
        """
        存储交易经验

        Args:
            experience: 交易经验对象

        Returns:
            经验ID
        """
        try:
            if not self.qdrant:
                await self.initialize()

            # 如果没有提供embedding，生成一个
            if experience.situation_embedding is None:
                embedding = await self._generate_embedding(experience.situation)
            else:
                embedding = experience.situation_embedding

            # 如果没有ID，生成一个
            if not experience.id:
                experience.id = str(uuid.uuid4())

            # 创建点
            point = PointStruct(
                id=experience.id,
                vector=embedding,
                payload=self._experience_to_payload(experience)
            )

            # 存储到Qdrant
            await self.qdrant.upsert(
                collection_name=self.COLLECTION_NAME,
                points=[point]
            )

            self.logger.info(f"Stored experience: {experience.id}")
            return experience.id

        except Exception as e:
            raise TradingSystemError(
                message="Failed to store experience",
                details={"experience_id": experience.id},
                original_exception=e
            )

    async def search_similar_experiences(
        self,
        query: MemoryQuery
    ) -> List[TradingExperience]:
        """
        检索相似经验

        Args:
            query: 查询对象

        Returns:
            相似经验列表，按相似度排序
        """
        try:
            if not self.qdrant:
                await self.initialize()

            # 生成查询向量
            if query.query_embedding is None:
                query_vector = await self._generate_embedding(query.query_text)
            else:
                query_vector = query.query_embedding

            # 构建过滤条件
            filter_conditions = []

            # 过滤outcome
            if "outcome" in query.filters:
                filter_conditions.append(
                    FieldCondition(
                        key="outcome",
                        match=MatchValue(value=query.filters["outcome"])
                    )
                )

            # 过滤重要性分数
            if query.min_importance > 0:
                filter_conditions.append(
                    FieldCondition(
                        key="importance_score",
                        range=Range(gte=query.min_importance)
                    )
                )

            # 过滤标签
            if "tags" in query.filters:
                for tag in query.filters["tags"]:
                    filter_conditions.append(
                        FieldCondition(
                            key="tags",
                            match=MatchValue(value=tag)
                        )
                    )

            # 执行搜索
            search_result = await self.qdrant.search(
                collection_name=self.COLLECTION_NAME,
                query_vector=query_vector,
                limit=query.top_k,
                query_filter=Filter(must=filter_conditions) if filter_conditions else None
            )

            # 转换结果
            experiences = []
            for scored_point in search_result:
                experience = self._payload_to_experience(scored_point.payload)
                experiences.append(experience)

            self.logger.info(f"找到 {len(experiences)} 条相似经验")
            return experiences

        except Exception as e:
            raise TradingSystemError(
                message="Failed to search experiences",
                details={"query_text": query.query_text},
                original_exception=e
            )

    async def update_experience(
        self,
        experience_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        更新经验

        Args:
            experience_id: 经验ID
            updates: 更新字段

        Returns:
            是否成功
        """
        try:
            if not self.qdrant:
                await self.initialize()

            # 设置payload
            await self.qdrant.set_payload(
                collection_name=self.COLLECTION_NAME,
                payload=updates,
                points=[experience_id]
            )

            self.logger.info(f"Updated experience: {experience_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to update experience {experience_id}: {e}")
            return False

    async def delete_experience(
        self,
        experience_id: str
    ) -> bool:
        """
        删除经验

        Args:
            experience_id: 经验ID

        Returns:
            是否成功
        """
        try:
            if not self.qdrant:
                await self.initialize()

            await self.qdrant.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=[experience_id]
            )

            self.logger.info(f"Deleted experience: {experience_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete experience {experience_id}: {e}")
            return False

    async def get_experience_by_id(
        self,
        experience_id: str
    ) -> Optional[TradingExperience]:
        """
        根据ID获取经验

        Args:
            experience_id: 经验ID

        Returns:
            TradingExperience对象，不存在返回None
        """
        try:
            if not self.qdrant:
                await self.initialize()

            points = await self.qdrant.retrieve(
                collection_name=self.COLLECTION_NAME,
                ids=[experience_id]
            )

            if not points:
                return None

            return self._payload_to_experience(points[0].payload)

        except Exception as e:
            self.logger.error(f"Failed to get experience {experience_id}: {e}")
            return None

    async def get_collection_stats(self) -> dict:
        """
        获取集合统计信息

        Returns:
            统计信息字典
        """
        try:
            if not self.qdrant:
                await self.initialize()

            info = await self.qdrant.get_collection(self.COLLECTION_NAME)

            return {
                "total_points": info.points_count,
                "vector_size": info.config.params.vectors.size,
                "distance": info.config.params.vectors.distance.name
            }

        except Exception as e:
            self.logger.error(f"Failed to get collection stats: {e}")
            return {}

    async def clear_all_experiences(self) -> bool:
        """
        清空所有经验（谨慎使用！）

        Returns:
            是否成功
        """
        try:
            if not self.qdrant:
                await self.initialize()

            await self.qdrant.delete_collection(self.COLLECTION_NAME)
            await self.initialize()  # 重新创建集合

            self.logger.warning("Cleared all experiences")
            return True

        except Exception as e:
            self.logger.error(f"Failed to clear experiences: {e}")
            return False
