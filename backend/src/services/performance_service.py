"""
绩效服务

负责：
1. 定时计算并存储每日绩效指标
2. 提供统一的绩效查询接口
3. 格式化绩效数据供AI决策使用
"""

from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List
from decimal import Decimal
import asyncio
import statistics

from src.core.logger import get_logger
from src.services.database import DatabaseManager, TradingDAO
from src.services.database.models import PerformanceMetricsModel


# 配置常量
DAILY_CALC_TIME_HOUR = 0  # UTC时间每日计算时刻（小时）
DAILY_CALC_TIME_MINUTE = 10  # UTC时间每日计算时刻（分钟）
RETRY_INTERVAL_SECONDS = 3600  # 错误重试间隔（秒）
CACHE_TTL_REALTIME = 60  # 实时数据缓存时间（秒）
CACHE_TTL_HISTORICAL = 3600  # 历史数据缓存时间（秒）
RISK_FREE_RATE = 0.0  # 无风险利率（用于夏普比率计算）
ANNUALIZED_DAYS = 252  # 年化天数（交易日）


class PerformanceService:
    """绩效服务"""

    def __init__(self, db_manager: DatabaseManager, exchange_name: str = "binanceusdm", redis_client=None):
        self.logger = get_logger(self.__class__.__name__)
        self.db_manager = db_manager
        self.exchange_name = exchange_name
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._redis_client = redis_client  # 可选的Redis客户端

        # 缓存配置（使用常量）
        self._cache_ttl_realtime = CACHE_TTL_REALTIME
        self._cache_ttl_historical = CACHE_TTL_HISTORICAL

    async def start(self):
        """启动服务"""
        if self._running:
            self.logger.warning("PerformanceService already running")
            return

        self._running = True
        self.logger.info("PerformanceService started")

        # 启动定时任务
        self._task = asyncio.create_task(self._daily_calculation_loop())

    async def stop(self):
        """停止服务"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.logger.info("PerformanceService stopped")

    async def _daily_calculation_loop(self):
        """每日绩效计算循环（UTC时间）"""
        while self._running:
            try:
                # 计算当前UTC时间到明天凌晨指定时刻的等待时间
                now = datetime.now(timezone.utc)
                tomorrow = (now + timedelta(days=1)).replace(
                    hour=DAILY_CALC_TIME_HOUR,
                    minute=DAILY_CALC_TIME_MINUTE,
                    second=0,
                    microsecond=0
                )
                wait_seconds = (tomorrow - now).total_seconds()

                self.logger.info(f"等待 {wait_seconds/3600:.2f} 小时后执行每日绩效计算（UTC {DAILY_CALC_TIME_HOUR:02d}:{DAILY_CALC_TIME_MINUTE:02d}）")

                # 等待到明天凌晨
                await asyncio.sleep(wait_seconds)

                # 计算昨天的绩效（UTC时间）
                yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1))
                self.logger.info(f"开始计算 {yesterday} 的绩效指标")

                await self.calculate_and_save_daily_performance(yesterday)

                self.logger.info(f"完成 {yesterday} 的绩效计算")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"每日绩效计算失败: {e}", exc_info=True)
                # 出错后等待指定时间再重试
                await asyncio.sleep(RETRY_INTERVAL_SECONDS)

    async def calculate_and_save_daily_performance(
        self,
        target_date: date,
        force: bool = False
    ) -> Optional[PerformanceMetricsModel]:
        """
        计算并保存指定日期的绩效指标

        Args:
            target_date: 目标日期
            force: 是否强制重新计算（覆盖已有数据）

        Returns:
            PerformanceMetricsModel or None
        """
        session = None
        try:
            async with self.db_manager.get_session() as session:
                dao = TradingDAO(session)

                # 检查是否已存在
                if not force:
                    existing = await dao.get_performance_metrics(
                        start_date=target_date,
                        end_date=target_date,
                        exchange_name=self.exchange_name
                    )
                    if existing:
                        self.logger.info(f"{target_date} 的绩效指标已存在，跳过计算")
                        return existing[0] if existing else None

                # 计算绩效指标
                metrics = await self._calculate_metrics(target_date, target_date, dao)

                if not metrics:
                    self.logger.warning(f"{target_date} 没有足够数据计算绩效")
                    return None

                # 数据校验
                if not self._validate_metrics(metrics):
                    self.logger.error(f"{target_date} 的绩效指标数据异常，拒绝保存")
                    return None

                # 保存到数据库
                exchange_id = await dao._get_or_create_exchange_id(self.exchange_name)

                performance = PerformanceMetricsModel(
                    strategy_id=None,  # 暂时不关联策略
                    start_date=datetime.combine(target_date, datetime.min.time()),
                    end_date=datetime.combine(target_date, datetime.max.time()),
                    total_return=Decimal(str(metrics['total_return'])),
                    annualized_return=Decimal(str(metrics.get('annualized_return', 0))),
                    volatility=Decimal(str(metrics.get('volatility', 0))),
                    max_drawdown=Decimal(str(metrics['max_drawdown'])),
                    sharpe_ratio=Decimal(str(metrics['sharpe_ratio'])),
                    sortino_ratio=None,
                    calmar_ratio=None,
                    total_trades=metrics['total_trades'],
                    winning_trades=metrics['profitable_trades'],
                    losing_trades=metrics['losing_trades'],
                    win_rate=Decimal(str(metrics['win_rate'])),
                    avg_win=Decimal(str(metrics['average_profit'])),
                    avg_loss=Decimal(str(metrics['average_loss'])),
                    profit_factor=Decimal(str(metrics['profit_factor'])),
                    max_consecutive_wins=0,  # 需要额外计算
                    max_consecutive_losses=0,  # 需要额外计算
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None)  # 移除时区信息以匹配数据库
                )

                session.add(performance)
                await session.commit()

                self.logger.info(f"已保存 {target_date} 的绩效指标")
                return performance

        except Exception as e:
            self.logger.error(f"计算并保存绩效失败: {e}", exc_info=True)
            # 明确回滚
            if session:
                try:
                    await session.rollback()
                    self.logger.info(f"已回滚 {target_date} 的绩效保存操作")
                except Exception as rollback_error:
                    self.logger.error(f"回滚失败: {rollback_error}")
            return None

    async def _calculate_metrics(
        self,
        start_date: date,
        end_date: date,
        dao: TradingDAO
    ) -> Optional[Dict[str, Any]]:
        """
        计算指定日期范围的绩效指标

        Args:
            start_date: 开始日期
            end_date: 结束日期
            dao: 数据访问对象

        Returns:
            绩效指标字典
        """
        try:
            # 获取快照和交易数据
            snapshots = await dao.get_portfolio_snapshots(
                start_date=start_date,
                end_date=end_date,
                limit=None,  # 有日期范围时不限制
                exchange_name=self.exchange_name
            )

            closed_positions = await dao.get_closed_positions(
                start_date=start_date,
                end_date=end_date,
                limit=10000,
                exchange_name=self.exchange_name
            )

            # 数据不足
            if len(snapshots) < 1 or len(closed_positions) < 1:
                return None

            # 计算收益
            initial_value = float(snapshots[-1].total_value) if snapshots else 0
            current_value = float(snapshots[0].total_value) if snapshots else 0
            total_return = current_value - initial_value
            total_return_percentage = (total_return / initial_value * 100) if initial_value > 0 else 0

            # 计算最大回撤
            values = [float(s.total_value) for s in reversed(snapshots)]
            max_drawdown = 0
            peak = values[0]
            for value in values:
                if value > peak:
                    peak = value
                drawdown = value - peak
                if drawdown < max_drawdown:
                    max_drawdown = drawdown

            # 计算夏普比率
            returns = []
            for i in range(1, len(values)):
                daily_return = (values[i] - values[i-1]) / values[i-1]
                returns.append(daily_return)

            avg_return = statistics.mean(returns) if returns else 0
            std_return = statistics.stdev(returns) if len(returns) > 1 else 0.01
            sharpe_ratio = (avg_return / std_return * (ANNUALIZED_DAYS ** 0.5)) if std_return > 0 else 0

            # 计算交易统计
            total_trades = len(closed_positions)
            profitable_trades = sum(1 for cp in closed_positions if float(cp.realized_pnl) > 0)
            losing_trades = sum(1 for cp in closed_positions if float(cp.realized_pnl) < 0)
            win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0.0

            # 计算平均盈亏
            profits = [float(cp.realized_pnl) for cp in closed_positions if float(cp.realized_pnl) > 0]
            losses = [float(cp.realized_pnl) for cp in closed_positions if float(cp.realized_pnl) < 0]
            average_profit = statistics.mean(profits) if profits else 0.0
            average_loss = statistics.mean(losses) if losses else 0.0

            # 计算盈亏比
            total_profit = sum(profits) if profits else 0.0
            total_loss = abs(sum(losses)) if losses else 0.0
            profit_factor = (total_profit / total_loss) if total_loss > 0 else 0.0

            return {
                'total_return': total_return,
                'total_return_percentage': total_return_percentage,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown,
                'max_drawdown_percentage': (max_drawdown / peak * 100) if peak > 0 else 0,
                'win_rate': win_rate,
                'total_trades': total_trades,
                'profitable_trades': profitable_trades,
                'losing_trades': losing_trades,
                'average_profit': average_profit,
                'average_loss': average_loss,
                'profit_factor': profit_factor,
            }

        except Exception as e:
            self.logger.error(f"计算绩效指标失败: {e}", exc_info=True)
            return None

    async def get_performance_summary(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        获取绩效摘要（混合查询：历史从表，当天实时计算）

        Args:
            start_date: 开始日期
            end_date: 结束日期
            use_cache: 是否使用缓存

        Returns:
            绩效摘要字典
        """
        # 尝试从缓存读取
        if use_cache and self._redis_client:
            try:
                cache_key = self._get_cache_key("summary", start_date, end_date)
                cached_data = await self._get_from_cache(cache_key)
                if cached_data:
                    self.logger.debug(f"从缓存获取绩效摘要: {cache_key}")
                    return cached_data
            except Exception as e:
                self.logger.warning(f"读取缓存失败: {e}")

        try:
            today = date.today()

            async with self.db_manager.get_session() as session:
                dao = TradingDAO(session)

                # 如果用户明确指定了end_date，且end_date早于今天
                # 返回那个历史时间范围的固定数据
                if end_date is not None and end_date < today:
                    # 直接从快照计算历史数据
                    return await self._aggregate_metrics_with_snapshots([], start_date, end_date)

                # 如果没有指定end_date，或者end_date是今天或之后
                # 则包含今天的实时数据
                end_date = end_date or today
                yesterday = today - timedelta(days=1)

                # 读取历史数据（如果不指定start_date，查询所有历史）
                historical_metrics = []
                if not start_date or start_date < today:
                    historical_metrics = await dao.get_performance_metrics(
                        start_date=start_date,  # None表示查询所有
                        end_date=yesterday,
                        exchange_name=self.exchange_name
                    )

                # 实时计算当天数据（仅当end_date未指定或等于今天时）
                today_metrics = await self._calculate_metrics(today, today, dao)

                # 合并结果
                all_metrics = []
                if historical_metrics:
                    all_metrics.extend(historical_metrics)

                # 如果今天有数据，也包含进来
                if today_metrics and today_metrics['total_trades'] > 0:
                    # 将今天的dict转为类似数据库模型的结构用于聚合
                    from types import SimpleNamespace
                    today_obj = SimpleNamespace(
                        total_return=today_metrics['total_return'],
                        max_drawdown=today_metrics['max_drawdown'],
                        sharpe_ratio=today_metrics['sharpe_ratio'],
                        total_trades=today_metrics['total_trades'],
                        winning_trades=today_metrics['profitable_trades'],
                        losing_trades=today_metrics['losing_trades'],
                        win_rate=today_metrics['win_rate'],
                        avg_win=today_metrics['average_profit'],
                        avg_loss=today_metrics['average_loss'],
                        profit_factor=today_metrics['profit_factor'],
                    )
                    all_metrics.append(today_obj)

                result = None
                if all_metrics:
                    result = await self._aggregate_metrics_with_snapshots(all_metrics, start_date, end_date, dao)
                else:
                    result = self._empty_metrics()

                # 保存到缓存
                if use_cache and self._redis_client and result:
                    try:
                        cache_key = self._get_cache_key("summary", start_date, end_date)
                        # 根据日期决定TTL
                        ttl = self._cache_ttl_realtime if end_date is None or end_date >= today else self._cache_ttl_historical
                        await self._save_to_cache(cache_key, result, ttl)
                    except Exception as e:
                        self.logger.warning(f"保存缓存失败: {e}")

                return result

        except Exception as e:
            self.logger.error(f"获取绩效摘要失败: {e}", exc_info=True)
            return self._empty_metrics()

    async def _aggregate_metrics_with_snapshots(
        self,
        metrics_list: List[Any],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        dao: Optional[TradingDAO] = None
    ) -> Dict[str, Any]:
        """
        聚合多条绩效记录（包含快照数据计算收益率）

        将多天的绩效数据聚合为整体统计
        如果metrics_list为空，则从快照和closed_positions直接计算

        Args:
            metrics_list: 绩效指标列表
            start_date: 开始日期
            end_date: 结束日期
            dao: 可选的数据访问对象，如果提供则复用，否则创建新的
        """
        # 初始化变量
        total_trades = 0
        profitable_trades = 0
        losing_trades = 0
        win_rate = 0
        average_profit = 0
        average_loss = 0
        profit_factor = 0
        max_drawdown = 0
        sharpe_ratio = 0

        # 如果有metrics_list，从中聚合统计
        if metrics_list:
            total_trades = sum(int(getattr(m, 'total_trades', 0) or 0) for m in metrics_list)
            profitable_trades = sum(int(getattr(m, 'winning_trades', 0) or 0) for m in metrics_list)
            losing_trades = sum(int(getattr(m, 'losing_trades', 0) or 0) for m in metrics_list)

            # 计算聚合后的统计指标
            win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0

            # 计算平均盈利和亏损（加权平均）
            total_avg_win = sum(float(getattr(m, 'avg_win', 0) or 0) * int(getattr(m, 'winning_trades', 0) or 0) for m in metrics_list)
            average_profit = (total_avg_win / profitable_trades) if profitable_trades > 0 else 0

            total_avg_loss = sum(float(getattr(m, 'avg_loss', 0) or 0) * int(getattr(m, 'losing_trades', 0) or 0) for m in metrics_list)
            average_loss = (total_avg_loss / losing_trades) if losing_trades > 0 else 0

            # 盈亏比
            total_profit = average_profit * profitable_trades if profitable_trades > 0 else 0
            total_loss = abs(average_loss * losing_trades) if losing_trades > 0 else 0
            profit_factor = (total_profit / total_loss) if total_loss > 0 else 0

            # 最大回撤：取所有天中最大的回撤
            max_drawdown = min((float(getattr(m, 'max_drawdown', 0) or 0) for m in metrics_list), default=0)

            # 夏普比率：简单平均（更准确应该用所有日收益率重新计算，但这里简化）
            sharpe_values = [float(getattr(m, 'sharpe_ratio', 0) or 0) for m in metrics_list if getattr(m, 'sharpe_ratio', None)]
            sharpe_ratio = sum(sharpe_values) / len(sharpe_values) if sharpe_values else 0

        # 从快照和closed_positions重新计算
        total_return = 0
        total_return_percentage = 0
        max_drawdown_percentage = 0

        # 会话管理优化：复用外部传入的dao或创建新的
        should_close_session = False
        if dao is None:
            session_context = self.db_manager.get_session()
            session = await session_context.__aenter__()
            dao = TradingDAO(session)
            should_close_session = True

        try:
            # 如果metrics_list为空，使用数据库聚合函数直接计算交易统计（优化性能）
            if not metrics_list:
                trade_stats = await self._calculate_trade_stats_from_db(dao, start_date, end_date)
                if trade_stats:
                    total_trades = trade_stats['total_trades']
                    profitable_trades = trade_stats['profitable_trades']
                    losing_trades = trade_stats['losing_trades']
                    win_rate = trade_stats['win_rate']
                    average_profit = trade_stats['average_profit']
                    average_loss = trade_stats['average_loss']
                    profit_factor = trade_stats['profit_factor']

            # 获取快照数据
            snapshots = await dao.get_portfolio_snapshots(
                start_date=start_date,
                end_date=end_date,
                limit=None,  # 有日期范围时不限制
                exchange_name=self.exchange_name
            )

            # 如果快照不足2个，且查询的是单日数据，尝试获取前一天的最后快照
            if snapshots and len(snapshots) < 2 and start_date and end_date and start_date == end_date:
                # 获取前一天的最后一个快照作为初始值
                from datetime import timedelta
                previous_day = start_date - timedelta(days=1)
                previous_snapshots = await dao.get_portfolio_snapshots(
                    start_date=previous_day,
                    end_date=previous_day,
                    limit=1,  # 只要最新的一个
                    exchange_name=self.exchange_name
                )
                if previous_snapshots:
                    # 将前一天的快照添加到列表末尾（作为初始值）
                    snapshots.append(previous_snapshots[0])
                    self.logger.debug(f"单日查询快照不足，补充前一天快照: {previous_snapshots[0].datetime}")

            if snapshots and len(snapshots) >= 1:
                # 最新快照在前
                current_value = float(snapshots[0].total_value)

                # 判断是否查询的是单日数据
                is_single_day_query = start_date and end_date and start_date == end_date

                # 如果查询的是单日数据且有多个快照（包含前一天补充的），使用最早的快照作为初始值
                if is_single_day_query and len(snapshots) > 1:
                    # 最早快照在末尾（前面的代码已经补充了前一天的快照）
                    initial_value = float(snapshots[-1].total_value)
                    self.logger.debug(f"单日查询，使用前一日收盘价作为初始值: {initial_value}")
                else:
                    # 多日查询或全部查询，尝试从数据库获取配置的初始资金
                    from sqlalchemy import text
                    result = await dao.session.execute(
                        text("SELECT initial_capital FROM account_settings WHERE exchange_id = :exchange_id"),
                        {"exchange_id": snapshots[0].exchange_id}
                    )
                    account_setting = result.fetchone()

                    if account_setting and float(account_setting[0]) > 0:
                        # 使用配置的初始资金
                        initial_value = float(account_setting[0])
                        self.logger.debug(f"使用配置的初始资金: {initial_value}")
                    elif len(snapshots) > 1:
                        # 降级：使用最早快照作为初始值
                        initial_value = float(snapshots[-1].total_value)
                        self.logger.debug(f"使用最早快照作为初始资金: {initial_value}")
                    else:
                        # 只有一个快照，无法计算
                        initial_value = current_value
                        self.logger.warning("只有一个快照且无初始资金配置，无法计算收益")

                # 总收益 = 当前价值 - 初始价值
                total_return = current_value - initial_value

                if initial_value > 0:
                    total_return_percentage = total_return / initial_value * 100

                # 计算最大回撤和夏普比率（如果metrics_list为空）
                if not metrics_list:
                    import statistics

                    values = [float(s.total_value) for s in reversed(snapshots)]

                    # 计算最大回撤（修复边界条件）
                    if len(values) > 0:
                        peak = values[0]
                        for value in values:
                            if value > peak:
                                peak = value
                            drawdown = value - peak
                            if drawdown < max_drawdown:
                                max_drawdown = drawdown

                        # 计算回撤百分比
                        if max_drawdown != 0 and peak > 0:
                            max_drawdown_percentage = (max_drawdown / peak) * 100

                    # 计算夏普比率（修复除零风险）
                    returns = []
                    for i in range(1, len(values)):
                        if values[i-1] != 0:  # 防止除零
                            daily_return = (values[i] - values[i-1]) / values[i-1]
                            returns.append(daily_return)

                    if len(returns) > 1:
                        avg_return = statistics.mean(returns)
                        std_return = statistics.stdev(returns)
                        sharpe_ratio = (avg_return / std_return * (ANNUALIZED_DAYS ** 0.5)) if std_return > 0 else 0
                    elif len(returns) == 1:
                        # 只有一天数据，无法计算标准差
                        sharpe_ratio = 0
                else:
                    # 如果有metrics_list，只计算回撤百分比
                    if max_drawdown != 0 and len(snapshots) > 0:
                        values = [float(s.total_value) for s in reversed(snapshots)]
                        peak = max(values) if values else 0
                        if peak > 0:
                            max_drawdown_percentage = (max_drawdown / peak) * 100
        except Exception as e:
            self.logger.warning(f"计算收益率失败: {e}", exc_info=True)
        finally:
            # 清理会话
            if should_close_session and dao and dao.session:
                await dao.session.close()

        return {
            'total_return': total_return,
            'total_return_percentage': total_return_percentage,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'max_drawdown_percentage': max_drawdown_percentage,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'profitable_trades': profitable_trades,
            'losing_trades': losing_trades,
            'average_profit': average_profit,
            'average_loss': average_loss,
            'profit_factor': profit_factor,
        }

    async def _calculate_trade_stats_from_db(
        self,
        dao: TradingDAO,
        start_date: Optional[date],
        end_date: Optional[date]
    ) -> Optional[Dict[str, Any]]:
        """
        使用数据库聚合函数直接计算交易统计（性能优化）

        Args:
            dao: 数据访问对象
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            交易统计字典
        """
        try:
            from sqlalchemy import text, and_
            from datetime import datetime

            # 构建查询条件
            filters = ["exchange_id = (SELECT id FROM exchanges WHERE name = :exchange_name)"]
            params = {"exchange_name": self.exchange_name}

            if start_date:
                filters.append("exit_time >= :start_time")
                params["start_time"] = datetime.combine(start_date, datetime.min.time())

            if end_date:
                filters.append("exit_time <= :end_time")
                params["end_time"] = datetime.combine(end_date, datetime.max.time())

            where_clause = " AND ".join(filters)

            # 使用数据库聚合函数计算统计数据
            query = text(f"""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as profitable_trades,
                    SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                    AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_profit,
                    AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss,
                    SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0 END) as total_profit,
                    SUM(CASE WHEN realized_pnl < 0 THEN ABS(realized_pnl) ELSE 0 END) as total_loss
                FROM closed_positions
                WHERE {where_clause}
            """)

            result = await dao.session.execute(query, params)
            row = result.fetchone()

            if not row or row[0] == 0:  # total_trades == 0
                return None

            total_trades = int(row[0] or 0)
            profitable_trades = int(row[1] or 0)
            losing_trades = int(row[2] or 0)
            avg_profit = float(row[3] or 0)
            avg_loss = float(row[4] or 0)
            total_profit = float(row[5] or 0)
            total_loss = float(row[6] or 0)

            win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
            profit_factor = (total_profit / total_loss) if total_loss > 0 else 0

            return {
                'total_trades': total_trades,
                'profitable_trades': profitable_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'average_profit': avg_profit,
                'average_loss': avg_loss,
                'profit_factor': profit_factor,
            }

        except Exception as e:
            self.logger.warning(f"数据库聚合计算失败，降级到Python计算: {e}")
            # 降级到原有的Python计算方式
            closed_positions = await dao.get_closed_positions(
                start_date=start_date,
                end_date=end_date,
                limit=10000,
                exchange_name=self.exchange_name
            )

            if not closed_positions:
                return None

            import statistics

            total_trades = len(closed_positions)
            profitable_trades = sum(1 for cp in closed_positions if float(cp.realized_pnl) > 0)
            losing_trades = sum(1 for cp in closed_positions if float(cp.realized_pnl) < 0)
            win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0

            profits = [float(cp.realized_pnl) for cp in closed_positions if float(cp.realized_pnl) > 0]
            losses = [float(cp.realized_pnl) for cp in closed_positions if float(cp.realized_pnl) < 0]
            average_profit = statistics.mean(profits) if profits else 0
            average_loss = statistics.mean(losses) if losses else 0

            total_profit = sum(profits) if profits else 0
            total_loss = abs(sum(losses)) if losses else 0
            profit_factor = (total_profit / total_loss) if total_loss > 0 else 0

            return {
                'total_trades': total_trades,
                'profitable_trades': profitable_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'average_profit': average_profit,
                'average_loss': average_loss,
                'profit_factor': profit_factor,
            }

    def _validate_metrics(self, metrics: Dict[str, Any]) -> bool:
        """
        校验绩效指标数据的合理性

        Args:
            metrics: 绩效指标字典

        Returns:
            True if valid, False otherwise
        """
        try:
            # 校验胜率范围
            if not (0 <= metrics.get('win_rate', 0) <= 100):
                self.logger.error(f"胜率异常: {metrics.get('win_rate')}")
                return False

            # 校验交易次数
            total_trades = metrics.get('total_trades', 0)
            profitable_trades = metrics.get('profitable_trades', 0)
            losing_trades = metrics.get('losing_trades', 0)

            if total_trades < 0 or profitable_trades < 0 or losing_trades < 0:
                self.logger.error(f"交易次数为负: total={total_trades}, profit={profitable_trades}, loss={losing_trades}")
                return False

            # 校验交易次数一致性
            if profitable_trades + losing_trades > total_trades:
                self.logger.error(f"盈利+亏损次数 > 总次数: {profitable_trades} + {losing_trades} > {total_trades}")
                return False

            # 校验盈亏比
            profit_factor = metrics.get('profit_factor', 0)
            if profit_factor < 0:
                self.logger.error(f"盈亏比为负: {profit_factor}")
                return False

            # 校验回撤（应该是负数或0）
            max_drawdown = metrics.get('max_drawdown', 0)
            if max_drawdown > 0:
                self.logger.warning(f"最大回撤为正数（可能正常）: {max_drawdown}")

            return True

        except Exception as e:
            self.logger.error(f"数据校验失败: {e}", exc_info=True)
            return False

    def _get_cache_key(self, prefix: str, start_date: Optional[date], end_date: Optional[date]) -> str:
        """生成缓存键"""
        start_str = start_date.isoformat() if start_date else "all"
        end_str = end_date.isoformat() if end_date else "today"
        return f"perf:{self.exchange_name}:{prefix}:{start_str}:{end_str}"

    async def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """从Redis缓存读取"""
        if not self._redis_client:
            return None
        try:
            import json
            data = await self._redis_client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            self.logger.debug(f"缓存读取失败 {key}: {e}")
        return None

    async def _save_to_cache(self, key: str, value: Dict[str, Any], ttl: int):
        """保存到Redis缓存"""
        if not self._redis_client:
            return
        try:
            import json
            await self._redis_client.setex(key, ttl, json.dumps(value))
            self.logger.debug(f"已缓存 {key} (TTL={ttl}s)")
        except Exception as e:
            self.logger.debug(f"缓存保存失败 {key}: {e}")

    def _empty_metrics(self) -> Dict[str, Any]:
        """返回空的绩效指标"""
        return {
            'total_return': 0.0,
            'total_return_percentage': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'max_drawdown_percentage': 0.0,
            'win_rate': 0.0,
            'total_trades': 0,
            'profitable_trades': 0,
            'losing_trades': 0,
            'average_profit': 0.0,
            'average_loss': 0.0,
            'profit_factor': 0.0,
        }

    async def format_for_ai(
        self,
        period: str = "recent",  # recent/daily/weekly/monthly
        include_details: bool = False
    ) -> str:
        """
        格式化绩效数据供AI使用

        Args:
            period: 时间周期
            include_details: 是否包含详细信息

        Returns:
            格式化的文本
        """
        try:
            # 确定时间范围
            today = date.today()
            if period == "daily":
                start_date = today
                end_date = today
            elif period == "weekly":
                start_date = today - timedelta(days=7)
                end_date = today
            elif period == "monthly":
                start_date = today - timedelta(days=30)
                end_date = today
            else:  # recent - 最近3天
                start_date = today - timedelta(days=3)
                end_date = today

            # 获取绩效数据
            metrics = await self.get_performance_summary(start_date, end_date)

            # 格式化文本
            text = f"""
## 绩效摘要 ({period})

**收益情况:**
- 总收益: ${metrics['total_return']:.2f} ({metrics['total_return_percentage']:.2f}%)
- 最大回撤: ${metrics['max_drawdown']:.2f} ({metrics['max_drawdown_percentage']:.2f}%)
- 夏普比率: {metrics['sharpe_ratio']:.2f}

**交易统计:**
- 总交易次数: {metrics['total_trades']}
- 盈利次数: {metrics['profitable_trades']} | 亏损次数: {metrics['losing_trades']}
- 胜率: {metrics['win_rate']:.2f}%
- 平均盈利: ${metrics['average_profit']:.2f} | 平均亏损: ${metrics['average_loss']:.2f}
- 盈亏比: {metrics['profit_factor']:.2f}

**绩效评估:**
"""
            # 添加评估
            if metrics['win_rate'] >= 60:
                text += "- ✅ 胜率优秀\n"
            elif metrics['win_rate'] >= 50:
                text += "- ⚠️ 胜率一般\n"
            else:
                text += "- ❌ 胜率较低，需要优化策略\n"

            if metrics['sharpe_ratio'] >= 2:
                text += "- ✅ 风险调整收益优秀\n"
            elif metrics['sharpe_ratio'] >= 1:
                text += "- ⚠️ 风险调整收益一般\n"
            else:
                text += "- ❌ 风险调整收益较差\n"

            if metrics['profit_factor'] >= 2:
                text += "- ✅ 盈亏比优秀\n"
            elif metrics['profit_factor'] >= 1.5:
                text += "- ⚠️ 盈亏比一般\n"
            else:
                text += "- ❌ 盈亏比较低\n"

            return text.strip()

        except Exception as e:
            self.logger.error(f"格式化AI数据失败: {e}", exc_info=True)
            return "绩效数据获取失败"

    async def get_recent_performance_trend(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        获取最近N天的绩效趋势

        Args:
            days: 天数

        Returns:
            每日绩效列表
        """
        try:
            end_date = date.today()
            start_date = end_date - timedelta(days=days)

            async with self.db_manager.get_session() as session:
                dao = TradingDAO(session)
                metrics = await dao.get_performance_metrics(
                    start_date=start_date,
                    end_date=end_date,
                    exchange_name=self.exchange_name
                )

                return [
                    {
                        'date': m.start_date.isoformat() if hasattr(m.start_date, 'isoformat') else str(m.start_date),
                        'return': float(m.total_return or 0),
                        'win_rate': float(m.win_rate or 0),
                        'trades': m.total_trades or 0,
                    }
                    for m in metrics
                ]

        except Exception as e:
            self.logger.error(f"获取绩效趋势失败: {e}", exc_info=True)
            return []
