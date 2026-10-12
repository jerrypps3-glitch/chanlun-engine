# -*- coding: utf-8 -*-
"""chanlun-engine 快速演示 — 零依赖跑通全管线。

用法: python demo.py
"""
from kline_chanlun_engine import KlineChanlunEngine, verify_origin


def main():
    # 0) 来源标记自检
    v = verify_origin()
    print(f"[来源] author={v['origin']['author']} engine={v['origin']['engine']} "
          f"license={v['origin']['license']} 完整性={'OK' if v['ok'] else '被改动!'}")

    # 1) 从 CSV 装载 (自带宽幅震荡合成样本, 便于稳定复现)
    e = KlineChanlunEngine.from_csv("sample", "samples/sample_daily.csv")
    print(f"\n[数据] {len(e.data)} 根K线, {e.data[0]['date']} ~ {e.data[-1]['date']}")

    # 2) 跑全管线
    e.run()

    # 3) 输出一览
    print(f"\n[管线] 合并K线={len(e._mk)}  笔={len(e.bi_list)}  段={len(e.segment_list)}")
    print(f"       笔中枢={len(e._zs_bi)}  段中枢={len(e._zs_seg)}  "
          f"MACD={len(e.macd)}  买卖点={len(e.signals)}")

    if e.bi_list:
        b = e.bi_list[-1]  # 最后一笔
        print(f"\n[最后一笔] {b['from']['date']}({b['from']['price']}) → "
              f"{b['to']['date']}({b['to']['price']})")

    if e._zs_bi:
        z = e._zs_bi[-1]  # 最后一个笔中枢
        print(f"[最后笔中枢] 区间 ZD={z['ZD']:.2f} ~ ZG={z['ZG']:.2f}  来源标记={z.get('_src')}")

    for s in e.signals[:5]:
        print(f"[买卖点] {s.get('type')} @ {s.get('price')} type字段口径见 README")

    print("\n✅ demo 跑通。用你自己的数据替换 samples/sample_daily.csv 即可分析任意品种。")


if __name__ == "__main__":
    main()
