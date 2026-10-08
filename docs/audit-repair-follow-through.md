# 审查修复说明

基于 `21e320f` 继续修复，保留该提交已有的不可识别结果展示、归因文件签名及强刷入口。

- 历史权重默认只接受请求日之前已生效的版本。无版本时，报告显示“历史权重不可用”；未来权重近似需要显式指定 `allow_future_fallback=True`。跳过缓存或强刷也必须遵守日期边界。
- 快照按真实生效日期排序，不按缓存文件名排序。清理重复缓存时保留每个历史版本的至少一份快照。并发读取采用锁和独立临时文件；读取相同内容不会修改文件时间。
- 报告缓存涵盖所有行情层、JSON/YAML 配置与权重快照。强刷在并发任务开始前清理归因缓存。新增权重快照在报告签名生成前准备。
- 行情新鲜度按纽约时区及 NYSE 的真实收盘时间判断，包括休市与提前收盘，保留收盘后 15 分钟的数据等待窗口。实现使用 [pandas-market-calendars 的交易日与收盘日历](https://pandas-market-calendars.readthedocs.io/en/latest/usage.html)。
- 近似反事实与 CATE 使用 DAG 后门控制集合，避免把处理后的中介变量放入控制集合；缺失必要控制变量时停止因果计算。CATE 缓存加入 DAG 指纹。
- 默认测试生成隔离的合成行情，参数是测试模型的已知真值，不代表真实市场数据。测试不改写项目行情或权重文件，禁用外部请求。

## 运行测试

```console
python -m pip install -r requirements-lock.txt
python -m pip install -e .
python -m pytest tests -q
```

三个真实行情服务测试默认跳过，按需运行：

```console
python -m pytest tests -m integration --integration -v
```

GitHub Actions 默认在 Python 3.11/3.12 上运行离线测试；手动触发工作流并开启 `live_data` 可运行独立的联网测试任务。联网结果受外部服务可用性影响。

新增流程测试覆盖历史权重缺失、日期与文件名冲突、历史版本保留、报告展示、各行情层缓存失效、并发快照、总效应恢复和纽约交易时段边界。修复前已观察到对应失败，再修改实现。
