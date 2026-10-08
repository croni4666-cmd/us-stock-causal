# 图表profile与option

此文件是项目skill的图表选择参考。预设与校验的运行时来源是`src/chart_profiles.py`；实际可用配置以`python -m examples.chart --list-profiles`为准。

## 预设

| profile | 默认标的与布局 | 图中均线 | 参考价 | 独立检查 |
|---|---|---|---|---|
| `price` | GC=F，单图，252观察日 | 无 | 无 | 默认关闭 |
| `ma-review` | GC=F，单图，252观察日 | 50/100/200 | 无 | 开启，检查50/100/200 |
| `comparison` | GC=F、GLD、QQQ、TLT，网格，252观察日 | 200 | 无 | 开启，各标的检查50/100/200 |
| `technical` | GC=F，单图，500观察日 | 20/50/100/150/200 | R1/S1 | 开启，检查50/100/200 |

所有预设都没有宏观事件叠线。显式option覆盖预设，不修改预设本身。多个标的默认使用网格；显式选`single`时须只有一个标的。

## 可选项

| option | 作用与范围 |
|---|---|
| `--symbols GC=F,GLD,QQQ,IEF,TLT` | 1–12个已支持的唯一标的；支持黄金期货、已列ETF及`^IXIC`指数。TNX是收益率报价，不能当债券价格图。 |
| `--layout single/grid` | 单图或网格；与标的数量匹配。 |
| `--lookback 500` | 图中显示的可用日线数，2–20000；均线预热及历史搜索仍可使用显示窗口之前的已加载数据。 |
| `--smas 50,100,200` / `--smas none` | 图中均线周期；唯一整数2–5000，或完全不画。 |
| `--pivots` / `--no-pivots` | 显示或隐藏R1/S1；不影响独立均线检查。 |
| `--review` / `--no-review` | 开启或关闭图片外MD/JSON检查。 |
| `--review-windows 50,100,200` | 独立检查的周期，可与图上不同。 |
| `--recent 5` | 最近1–100个可用日线的穿越记录。 |
| `--cross-history all` / `--cross-history 100` | 最后穿线搜索全部已加载可计算历史，或限定最后N组相邻观察；默认all。 |
| `--as-of 2026-09-10` | 将数据截断至指定日期后再绘图、检查；周末等无报价日期取截至该日的最后可用记录。 |
| `--cache-root PATH` | 读取`PATH/<layer>/<safe_symbol>.parquet`；入口不自动联网。 |
| `--output PATH` | 图片文件名或stem；同名检查与manifest保存在旁边。纯图目标若已有旧检查文件，换一个输出名，避免旧报告被当作本次结果。 |
| `--formats png,svg,pdf` | 默认png；格式不得重复。SVG来源/ID检查见manifest；浏览器与人工验收另列。关键标签英文在前、中文解释在后；系统需有微软雅黑/Noto Sans CJK等中文字体。 |
| `--dpi 300` | PNG分辨率50–600dpi；提高分辨率不等于人工视觉验收。 |

缓存文件的真实来源与时序不由文件名、单位声明或哈希自动认证。CLI拒绝乱序、重复、缺少/非有限OHLC及不一致高低价；不悄悄填充或伪造数据。

## 一个完整例子

用户：“生成黄金均线图，最近10个观察日，并告诉我上次穿线；截止到9月10日，图上不要参考价。”

在用户指定的年份和真实缓存目录已明确时：

```console
python -m examples.chart --profile ma-review --symbols GC=F --recent 10 --cross-history all --as-of 2026-09-10 --no-pivots --cache-root PATH --output output/gold_ma_2026-09-10.png
```

`PATH`替换为实际已有缓存根目录，不能原样执行占位值。该请求没有要求盘中时间，不要用日线日期伪造小时/分钟。

另两种常见选择：`--profile price --review`只画价格但仍附检查；`--profile comparison --symbols GC=F,GLD,QQQ,IEF,TLT`对比五个不同报价口径的标的，不归一化成可互换价格。

## 读取本次结果

1. `.manifest.json`列出实际profile、覆盖项、数据路径/哈希、实际截至日、单位和本次产物。
2. `.ma-review.md/.json`区分最新收盘事件、近期记录、历史最后上穿/下穿和最近一次方向。
3. 最后穿线日期是两次可用收盘之间确认换边的后一个日期，同时保留前一个日期；不代表知道盘中穿越时刻。
4. 搜索范围没有记录、均线预热不足或中间缺数据时，保留限制，不从当前位置反推某次穿越日期。
5. 对图片做AI视觉观察后，把人工验收留给用户；不能将程序成功、skill校验或AI复核叫人工视觉通过。
