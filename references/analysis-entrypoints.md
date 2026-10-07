# 其他分析入口

仅在用户请求相应任务时使用，先确认已有数据及其日期。这些入口不是因果认证，也不替代图表profile。

| 任务 | 模块或命令 | 边界 |
|---|---|---|
| 数据读取、缓存、代理 | `src/data.py`、`src/cache.py`、`src/proxy.py`；`python -m examples.fetch_all` | 沿用实际环境配置，检查真实抓取结果，不宣称固定标的数量全部成功。 |
| 回报与价格阈值 | `src/returns.py`、`src/thresholds.py` | 核对价格、收益率、指数及期货单位；穿线日期用`src/chart_review.py`。 |
| 行业贡献及残差 | `src/attribution.py`、`src/residual.py` | 历史权重必须匹配观察时点；贡献与残差不等于因果识别。 |
| 历史形态匹配 | `src/patterns.py`；`python -m examples.patterns` | 相似历史与样本命中率不等于未来概率。 |
| 事件与信号摘要 | `src/events.py`、`src/signals.py` | 来源和日期需核验，保留矛盾；事件不叠加行情图，不根据同日关系认定因果。 |
| 宏观摘要及报告 | `src/macro.py`、`src/report.py`；`python -m examples.report` | 说明数据时点及模型边界；`src/kline.py`用于图形，选型优先统一profile CLI。 |
| 导出与自行分析 | `python -m examples.export`、`python -m examples.notebook` | 按用户指定格式和范围执行，不自动发布或开启额外服务。 |

可调用函数与参数以当前源码及各入口`--help`为准。需要官方持仓、每日权重或美债曲线时，读取主skill链接的资产专用文档。
