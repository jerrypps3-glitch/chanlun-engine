# chanlun-engine（缠论引擎 V2）

一个成熟稳定的**本地缠论引擎**，按缠论 108 课口径实现完整算法管线：

```
K线 → 包含处理 → 分型 → 笔 → 段(双破坏) → 中枢(3重叠) → MACD → 买卖点(BSP) → 走势分类
```

在多轮实战验证中沉淀而成，现放回开源社区——缠论是公共资产，人人可拿、可参与维护。

## 特性

- **零第三方依赖**：纯标准库（`sqlite3` / `csv` / `math` / `datetime`），clone 即跑
- **数据入口开放**：`load_records()`（内存）/ `from_csv()`（CSV）——不绑任何数据库
- **算法口径全注释**：中枢"3 个元素价格重叠+确认制"、段"双破坏"、BSP 主引擎口径，均可溯源
- **输出即数据**：笔/段/中枢/MACD/买卖点 全是纯字典列表，易于二次加工（画图/回测/对接）

## 快速开始

```python
from kline_chanlun_engine import KlineChanlunEngine

# 方式一: CSV（列名 date/open/high/low/close/volume; 也认 日期/开盘/... 中文表头）
e = KlineChanlunEngine.from_csv("demo", "samples/sample_daily.csv").run()

# 方式二: 内存记录（list[dict] 或 list[tuple]）
e = KlineChanlunEngine("demo").load_records([
    {"date": "20240102", "open": 10.0, "high": 11.0, "low": 9.8, "close": 10.6, "volume": 10000},
    # ...
]).run()

print(e.bi_list[0])        # 笔列表
print(e.segment_list[0])   # 段列表
print(e._zs_bi[0])         # 笔中枢
print(e.signals[:3])       # 买卖点信号
```

跑自带示例（含输出说明）：

```bash
python demo.py
```

## 数据格式

| 字段 | 要求 |
|---|---|
| `date` | `YYYYMMDD` 或 `YYYY-MM-DD`，升序不强制（装载时自动排序） |
| `open/high/low/close` | 正数；须满足 high ≥ low 等基本关系 |
| `volume` | 数值，单位不限（不影响缠论结构计算） |

自动防线：日期非法（长度≠8/月份>12 等）或 OHLC 非正的行**装载时静默过滤**（源数据脏行事故的沉淀）。

CSV 列名映射：支持标准英文列名与 `trade_date`/`vol` 等常见别名；中文表头（`日期/开盘/最高/最低/收盘/成交量`）自动识别。自定义列名用 `load_records(records, fields={'your_col': 'date', ...})`（约定：`{原始列名: 标准名}`）。

## 输出结构

| 属性 | 内容 |
|---|---|
| `e.data` | 清洗排序后的日线数据 |
| `e._mk` / `e.proc_klines` | 包含处理后的合并K线 |
| `e.bi_list` | 笔列表（`from`/`to` 端点含 idx/type/price/date） |
| `e.segment_list` | 段列表（方向/起止价/`sure` 确认标志） |
| `e._zs_bi` / `e._zs_seg` | 笔中枢 / 段中枢（`ZD`/`ZG`/`DD`/`GG` 区间） |
| `e.macd` | MACD 序列（与 K 线对齐） |
| `e.signals` / `e.bi_signals` | 买卖点（1B/2B/3B/1C/2C 等口径在信号 `type` 字段） |
| `e.trends` | 走势分类 |

## 来源与许可证

**Copyright (C) 2026 jerrypps3-glitch — GNU AGPL-3.0-or-later**

你可以自由使用、修改、分发本引擎；**但任何衍生作品（包括网络服务化）必须以 AGPL-3.0 开源全部源代码**并保留版权声明。闭源商用/去除声明即违反许可证。

引擎内嵌三层来源标记（源码声明 / 模块级 `__origin__` / 输出数据 `_src` 字段），可用 `verify_origin()` 验证任何副本的来源完整性：

```python
>>> from kline_chanlun_engine import verify_origin
>>> verify_origin()["ok"]
True
```

移除标记需要故意改动源码——那本身就是侵权证据。欢迎 fork、提 issue、参与维护。
