"""
缠论K线引擎 V2 — 标准108课算法管线 (2026-06-28 重写)
=================================================
K线 → 包含处理 → 分型 → 笔(108课) → 段(双破坏) → 中枢(3重叠) → BSP(主引擎移植)

Copyright (C) 2026 jerrypps3-glitch <https://github.com/jerrypps3-glitch/chanlun-engine>
SPDX-License-Identifier: AGPL-3.0-or-later

本文件以 GNU AGPL-3.0(或更新版本)发布: 你可以自由使用、修改、再分发,
但任何衍生作品(含网络服务化)必须以同一许可证开源全部源代码, 并保留本声明。
详见 LICENSE 文件。被移除本声明与本文件内嵌水印的副本 = 故意侵权证据。

算法: 标准缠论108课 (分型/笔/段/中枢/BSP 主引擎口径)
接口兼容: 保留原 KlineChanlunEngine 全部公开属性和方法签名
"""
import sqlite3, math, datetime

# ════════════════════════════════════════════════════════════
# 出品水印/来源标记 (三层防护之第②③层) — 详见 README「来源与许可证」
# 水印存在于每个中枢对象的 '_src' 字段与输出数据流中:
# 保留 = 来源身份跟随数据传播; 移除 = 需故意改动本文件 = 篡改痕迹
# ════════════════════════════════════════════════════════════
__origin__ = {
    "author": "jerrypps3-glitch",
    "project": "chanlun-engine",
    "url": "https://github.com/jerrypps3-glitch/chanlun-engine",
    "engine": "chanlun-v2",
    "license": "AGPL-3.0-or-later",
    "version": "2.0.0",
}
# 完整性锚: __origin__+引擎核心函数对象的签名指纹, 任何"删水印式"改动会使其失配
WATERMARK_CHECK = "f5744cad53983b76"


def verify_origin():
    """验证引擎来源标记完整性。返回 __origin__ 字典。

    对任何副本可调用本函数确认: 是否为本项目原始/合规衍生发布。
    若 WATERMARK_CHECK 失配 → 本文件已被未声明地改动。"""
    import hashlib
    probe = {
        "origin": __origin__,
        "fns": [merge_klines.__name__, detect_fractals.__name__, build_bi.__name__,
                build_segments.__name__, build_zhongshu.__name__, detect_bsp_seg.__name__],
    }
    fp = hashlib.sha256(
        repr(probe).replace("'", '"').encode("utf-8")
    ).hexdigest()
    return {"ok": fp[:16] == WATERMARK_CHECK, "checksum": fp[:16],
            "expected": WATERMARK_CHECK, "origin": dict(__origin__)}


# ============================================================
# L1: 包含处理
# ============================================================
def merge_klines(candles, initial_dir=None):
    """标准包含处理 — UP取高高, DOWN取低低"""
    if len(candles) < 2:
        return [{'start_time': candles[0].get('time', candles[0].get('date', '')),
                 'end_time': candles[0].get('time', candles[0].get('date', '')),
                 'high': candles[0]['high'], 'low': candles[0]['low'], 'dir': 'up', 'n': 1}]

    direction = initial_dir
    prev = {'high': candles[0]['high'], 'low': candles[0]['low'],
            'start_time': candles[0].get('time', candles[0].get('date', '')),
            'end_time': candles[0].get('time', candles[0].get('date', '')),
            'dir': None, 'n': 1}
    result = []

    for i in range(1, len(candles)):
        c = candles[i]
        cur = {'high': c['high'], 'low': c['low'],
               'start_time': c.get('time', c.get('date', '')),
               'end_time': c.get('time', c.get('date', '')), 'n': 1}

        if direction is None:
            new_dir = None
            if cur['high'] > prev['high'] and cur['low'] > prev['low']: new_dir = 'up'
            elif cur['high'] < prev['high'] and cur['low'] < prev['low']: new_dir = 'down'
            if new_dir:
                prev['dir'] = new_dir
                prev['start_time'] = candles[0].get('time', candles[0].get('date', ''))
                prev['end_time'] = candles[i-1].get('time', candles[i-1].get('date', ''))
                prev['n'] = 1 if i == 1 else prev['n']
                if i == 1:
                    prev['start_time'] = candles[0].get('time', candles[0].get('date', ''))
                    prev['end_time'] = candles[0].get('time', candles[0].get('date', ''))
                result.append(dict(prev))
                direction = new_dir
                prev = dict(cur); prev['dir'] = direction
            else:
                prev['high'] = max(prev['high'], cur['high'])
                prev['low'] = min(prev['low'], cur['low'])
                prev['end_time'] = cur['end_time']
                prev['n'] += 1
        else:
            has_inc = (cur['high'] <= prev['high'] and cur['low'] >= prev['low']) or \
                      (cur['high'] >= prev['high'] and cur['low'] <= prev['low'])
            if has_inc:
                if direction == 'up':
                    prev['high'] = max(prev['high'], cur['high'])
                    prev['low'] = max(prev['low'], cur['low'])
                else:
                    prev['high'] = min(prev['high'], cur['high'])
                    prev['low'] = min(prev['low'], cur['low'])
                prev['end_time'] = cur['end_time']
                prev['n'] += 1
                prev['dir'] = direction
            else:
                if prev.get('dir') is None and direction is not None:
                    prev['dir'] = direction
                result.append(dict(prev))
                if cur['high'] > prev['high'] and cur['low'] > prev['low']: direction = 'up'
                elif cur['high'] < prev['high'] and cur['low'] < prev['low']: direction = 'down'
                prev = dict(cur); prev['dir'] = direction

    if prev.get('dir') is None: prev['dir'] = direction or 'up'
    result.append(prev)
    return result


# ============================================================
# L2-L3: 分型 + 笔 (108课规则)
# ============================================================
def detect_fractals(mk):
    fractals = []
    for i in range(1, len(mk)-1):
        l, m, r = mk[i-1], mk[i], mk[i+1]
        if m['high'] > l['high'] and m['high'] > r['high']:
            fractals.append({'idx': i, 'type': 'top', 'price': m['high'], 'mk': m})
        if m['low'] < l['low'] and m['low'] < r['low']:
            fractals.append({'idx': i, 'type': 'bottom', 'price': m['low'], 'mk': m})
    return fractals


def build_bi(mk):
    fractals = detect_fractals(mk)
    n = len(fractals)
    if n < 2: return [], fractals

    def span_ok(s, e): return fractals[e]['idx'] - fractals[s]['idx'] >= 4
    def price_ok(s, e):
        sf, ef = fractals[s], fractals[e]
        if sf['type'] == 'top': return ef['type'] == 'bottom' and ef['price'] < sf['price']
        return ef['type'] == 'top' and ef['price'] > sf['price']

    def find_next(si):
        opp = 'bottom' if fractals[si]['type'] == 'top' else 'top'
        for j in range(si+1, n):
            if fractals[j]['type'] != opp: continue
            if not span_ok(si, j): continue
            if not price_ok(si, j): continue
            sup = False
            for k in range(j+1, n):
                fk = fractals[k]
                if fk['type'] != opp: continue
                if opp == 'bottom' and fk['price'] >= fractals[j]['price']: continue
                if opp == 'top' and fk['price'] <= fractals[j]['price']: continue
                has_rev = any(fractals[m]['type'] == fractals[si]['type'] and span_ok(j, m) and price_ok(j, m)
                             for m in range(j+1, k))
                if not has_rev: sup = True; break
            if not sup:
                return j
        return None

    bi_list = []
    pos = 0
    while pos < n:
        nxt = find_next(pos)
        if nxt is None:
            pos += 1
            continue
        sf, ef = fractals[pos], fractals[nxt]
        direction = 'down' if sf['type'] == 'top' else 'up'
        bi_list.append({
            'start_mk': sf['idx'], 'end_mk': ef['idx'],
            'start_price': sf['price'], 'end_price': ef['price'],
            'direction': direction,
            'start_time': sf['mk']['start_time'], 'end_time': ef['mk']['end_time'],
            'start_fx_idx': pos, 'end_fx_idx': nxt,
            'amp': abs(ef['price'] - sf['price']) / sf['price'] * 100,
        })
        pos = nxt

    return bi_list, fractals


# ============================================================
# L4: 段 — 特征序列分型 + 后向包含丢弃 (108课标准)
# ============================================================
def build_segments(bi_list):
    """特征序列分型法 + 后向包含丢弃"""
    if len(bi_list) < 3:
        return [{'start_bi': 0, 'end_bi': len(bi_list)-1,
                 'dir': bi_list[0]['direction'] if bi_list else 'up', 'sure': False}]

    segs = []
    start = 0
    seg_dir = bi_list[0]['direction']
    i = start + 1

    while i < len(bi_list):
        # 收集当前段内的特征序列(反向笔)
        features = []
        for j in range(start + 1, i + 1):
            if bi_list[j]['direction'] != seg_dir:
                lo = min(bi_list[j]['start_price'], bi_list[j]['end_price'])
                hi = max(bi_list[j]['start_price'], bi_list[j]['end_price'])
                features.append((j, lo, hi))

        # 第二种线段破坏 (71课): 第一特征元素突破段起点 → 段立即结束
        if len(features) == 1:
            f_idx, f_lo, f_hi = features[0]
            seg_start_price = bi_list[start]['start_price']
            if seg_dir == 'up' and f_lo < seg_start_price:
                end = f_idx - 1
                while end >= start and bi_list[end]['direction'] != seg_dir:
                    end -= 1
                if end >= start:
                    segs.append({'start_bi': start, 'end_bi': end, 'dir': seg_dir, 'sure': True})
                    start = end + 1
                    seg_dir = 'down'
                    i = start + 1
                    continue
            elif seg_dir == 'down' and f_hi > seg_start_price:
                end = f_idx - 1
                while end >= start and bi_list[end]['direction'] != seg_dir:
                    end -= 1
                if end >= start:
                    segs.append({'start_bi': start, 'end_bi': end, 'dir': seg_dir, 'sure': True})
                    start = end + 1
                    seg_dir = 'up'
                    i = start + 1
                    continue

        if len(features) >= 3:
            # 从后往前做包含丢弃: 被前一元素完全包含的丢弃
            # 弹出后原地重检一次(处理紧邻级联)
            f = list(features)
            idx = len(f) - 1
            while idx >= 1:
                popped = False
                if f[idx][1] >= f[idx-1][1] and f[idx][2] <= f[idx-1][2]:
                    f.pop(idx); popped = True
                    if idx >= len(f): idx = len(f) - 1
                if popped and idx >= 1 and idx < len(f):
                    if f[idx][1] >= f[idx-1][1] and f[idx][2] <= f[idx-1][2]:
                        f.pop(idx)
                        if idx >= len(f): idx = len(f) - 1
                idx -= 1

            if len(f) >= 3:
                f3 = f[-3:]
                (_, l_lo, l_hi), (mid_idx, m_lo, m_hi), (_, r_lo, r_hi) = f3

                # UP段 → 特征序列顶分型 → 段结束
                if seg_dir == 'up' and m_hi > l_hi and m_hi > r_hi:
                    end = mid_idx - 1
                    while end >= start and bi_list[end]['direction'] != seg_dir:
                        end -= 1
                    if end >= start:
                        segs.append({'start_bi': start, 'end_bi': end, 'dir': seg_dir, 'sure': True})
                        start = end + 1
                        seg_dir = 'down'
                        i = start + 1
                        continue
                # DOWN段 → 特征序列底分型 → 段结束
                elif seg_dir == 'down' and m_lo < l_lo and m_lo < r_lo:
                    end = mid_idx - 1
                    while end >= start and bi_list[end]['direction'] != seg_dir:
                        end -= 1
                    if end >= start:
                        segs.append({'start_bi': start, 'end_bi': end, 'dir': seg_dir, 'sure': True})
                        start = end + 1
                        seg_dir = 'up'
                        i = start + 1
                        continue

        i += 1

    # 最后一段 (未确认)
    if start < len(bi_list):
        best_end = len(bi_list) - 1
        for k in range(len(bi_list) - 1, start - 1, -1):
            if bi_list[k]['direction'] == seg_dir:
                if seg_dir == 'up' and bi_list[k]['end_price'] > bi_list[best_end]['end_price']:
                    best_end = k
                elif seg_dir == 'down' and bi_list[k]['end_price'] < bi_list[best_end]['end_price']:
                    best_end = k
        segs.append({'start_bi': start, 'end_bi': best_end, 'dir': seg_dir, 'sure': False})

    return segs


# ============================================================
# L5: 中枢 (通用: 笔中枢 + 段中枢)
# ============================================================
def build_zhongshu(items, key='bi'):
    """通用中枢: 至少3个元素价格重叠. key='bi' 或 'seg'"""
    if len(items) < 3: return []
    zs_list, i = [], 0
    while i <= len(items) - 3:
        # 确认制 (108课): 窗口三元素必须全部已确认(sure)，未确认段/笔不得作为中枢成立元素 (2026-09-02)
        if not all(it.get('sure', True) for it in items[i:i+3]):
            i += 1
            continue
        ranges = [(min(it['start_price'], it['end_price']), max(it['start_price'], it['end_price']))
                  for it in items[i:i+3]]
        lo, hi = max(r[0] for r in ranges), min(r[1] for r in ranges)
        if lo < hi:
            dd = min(min(it['start_price'], it['end_price']) for it in items[i:i+3])
            gg = max(max(it['start_price'], it['end_price']) for it in items[i:i+3])
            zs = {f'start_{key}': i, f'end_{key}': i+2, 'ZD': lo, 'ZG': hi, 'DD': dd, 'GG': gg,
                  '_src': {'engine': __origin__['engine'], 'by': __origin__['author'],
                           'repo': __origin__['project'], 'v': __origin__['version']}}
            j = i + 3
            while j < len(items):
                if not items[j].get('sure', True):
                    break  # 延伸元素也须已确认 (2026-09-02)
                j_lo = min(items[j]['start_price'], items[j]['end_price'])
                j_hi = max(items[j]['start_price'], items[j]['end_price'])
                if j_lo < zs['ZG'] and j_hi > zs['ZD']:
                    zs[f'end_{key}'] = j
                    zs['ZD'] = max(zs['ZD'], j_lo)
                    zs['ZG'] = min(zs['ZG'], j_hi)
                    zs['DD'] = min(zs['DD'], j_lo)
                    zs['GG'] = max(zs['GG'], j_hi)
                    j += 1
                else: break
            zs_list.append(zs)
            i = zs[f'end_{key}'] + 1
        else: i += 1
    return zs_list


def build_zhongshu_bi(bi_list):
    return build_zhongshu(bi_list, 'bi')


def build_zhongshu_seg(seg_list):
    items = [{'start_price': s['start_price'], 'end_price': s['end_price'],
              'sure': s.get('sure', True)} for s in seg_list]  # sure 必须透传，通用函数据此裁决 (2026-09-02)
    return build_zhongshu(items, 'seg')


# ============================================================
# L6: MACD
# ============================================================
def calc_macd_raw(closes, fast=12, slow=26, signal=9):
    n = len(closes)
    if n < 2: return [0]*n, [0]*n, [0]*n
    ema_fast = [closes[0]] * n; ema_slow = [closes[0]] * n
    for i in range(1, n):
        ema_fast[i] = closes[i] * (2/(fast+1)) + ema_fast[i-1] * (1-2/(fast+1))
        ema_slow[i] = closes[i] * (2/(slow+1)) + ema_slow[i-1] * (1-2/(slow+1))
    dif = [ema_fast[i] - ema_slow[i] for i in range(n)]
    dea = [dif[0]] * n
    for i in range(1, n): dea[i] = dif[i] * (2/(signal+1)) + dea[i-1] * (1-2/(signal+1))
    macd_hist = [(dif[i] - dea[i]) * 2 for i in range(n)]
    return dif, dea, macd_hist


# ============================================================
# L7: BSP — 主引擎 _detect_signals_for 完整移植
# ============================================================
def detect_bsp_seg(bi_list, segments, zs_bi_list, zs_seg_list, candles):
    signals = []
    acs = zs_bi_list
    if not acs or len(segments) < 2: return signals

    dif, dea, macd_hist = calc_macd_raw([c['close'] for c in candles])

    def seg_lo(si):
        s = segments[si] if isinstance(si, int) else si
        ds = [bi_list[i]['end_price'] for i in range(s['start_bi'], s['end_bi']+1) if bi_list[i]['direction']=='down']
        return min(ds) if ds else min(bi_list[i]['start_price'] for i in range(s['start_bi'], s['end_bi']+1))

    def seg_hi(si):
        s = segments[si] if isinstance(si, int) else si
        us = [bi_list[i]['end_price'] for i in range(s['start_bi'], s['end_bi']+1) if bi_list[i]['direction']=='up']
        return max(us) if us else max(bi_list[i]['start_price'] for i in range(s['start_bi'], s['end_bi']+1))

    def macd_sum(bi_s, bi_e):
        area = 0.0
        for idx in range(bi_s, min(bi_e+1, len(bi_list))):
            b = bi_list[idx]
            for k in range(max(0, b.get('start_mk',0)), min(len(macd_hist), b.get('end_mk',0)+1)):
                area += abs(macd_hist[k])
        if area > 0: return area
        return abs(seg_hi({'start_bi':bi_s,'end_bi':bi_e}) - seg_lo({'start_bi':bi_s,'end_bi':bi_e})) * (bi_e-bi_s+1)

    def find_bottom_bi(bi_s, bi_e):
        best_p = float('inf'); best = None
        for idx in range(bi_s, bi_e+1):
            b = bi_list[idx]
            if b['direction']=='down' and b['end_price'] < best_p:
                best_p = b['end_price']; best = (idx, best_p)
        return best

    def find_top_bi(bi_s, bi_e):
        best_p = float('-inf'); best = None
        for idx in range(bi_s, bi_e+1):
            b = bi_list[idx]
            if b['direction']=='down' and b['start_price'] > best_p:
                best_p = b['start_price']; best = (idx, best_p)
            if b['direction']=='up' and b['end_price'] > best_p:
                best_p = b['end_price']; best = (idx, best_p)
        return best

    # bi→段 映射表
    bi_to_seg = {}
    for si, s in enumerate(segments):
        for bidx in range(s['start_bi'], s['end_bi'] + 1):
            bi_to_seg[bidx] = si

    def edir_from_prev(i):
        c = acs[i]
        ss = bi_to_seg.get(c['start_bi'])
        if ss is not None and ss < len(segments):
            d = segments[ss].get('dir', '')
            if d in ('up', 'down'): return d
        if i == 0: return None
        pc = acs[i-1]
        if pc['ZG'] <= pc['ZD']: return None
        if pc['ZD'] > acs[i]['ZG']: return 'down'
        if pc['ZG'] < acs[i]['ZD']: return 'up'
        return None

    def prev_same_level(i):
        my_edir = edir_from_prev(i)
        if my_edir is None: return None
        for ci in range(i - 1, -1, -1):
            pc = acs[ci]
            if pc['ZG'] <= pc['ZD']: continue
            if my_edir == 'down' and pc['ZD'] > acs[i]['ZG']: return ci
            if my_edir == 'up' and pc['ZG'] < acs[i]['ZD']: return ci
        return None

    _seen = set()
    def add_sig(stype, ci, seg_idx, price):
        key = (seg_idx, stype)
        if key not in _seen:
            _seen.add(key)
            direction = 'buy' if stype in ('1B','2B','3B') else 'sell'
            signals.append({'type': stype, 'direction': direction,
                          'price': price, 'idx': seg_idx, 'level': 'seg'})
            return True
        return False

    has = {t: {} for t in ('1B','1C','2B','2C','3B','3C','S2')}

    for i, c in enumerate(acs):
        if c['ZG'] <= c['ZD']: continue
        zd, zg = c['ZD'], c['ZG']

        ss = bi_to_seg.get(c['start_bi'])
        es = bi_to_seg.get(c['end_bi'])
        if ss is None or es is None: continue

        entry_seg = segments[ss - 1] if ss > 0 else segments[ss]

        # ---- 扩张区检测 ----
        in_expansion = False
        expansion_edir = None
        if i > 0:
            pc = acs[i-1]
            if pc['ZG'] > pc['ZD']:
                if not (pc['ZG'] < c['ZD'] or pc['ZD'] > c['ZG']):
                    in_expansion = True
                    for ci in range(i - 1, -1, -1):
                        pe = edir_from_prev(ci)
                        if pe is not None: expansion_edir = pe; break

        # ---- 趋势判定 ----
        edir = expansion_edir if in_expansion else edir_from_prev(i)
        if edir is None:
            d = segments[ss].get('dir', '')
            if d in ('up', 'down'): edir = d
            else: continue

        prev_i = prev_same_level(i)

        # ---- 找离开段 ----
        exit_seg = None; exit_idx = None
        best_val = 0.0 if edir == 'up' else float('inf')
        for j in range(ss + 1, len(segments)):
            s = segments[j]
            if s['dir'] != edir: continue
            v = seg_hi(s) if edir == 'up' else seg_lo(s)
            if (edir == 'up' and v > zg and v > best_val) or (edir == 'down' and v < zd and v < best_val):
                exit_seg = s; exit_idx = j; best_val = v
        if exit_seg is None: continue
        exit_nbi = exit_seg['end_bi'] - exit_seg['start_bi'] + 1

        # ===== 1B: 趋势背驰买点 =====
        if not in_expansion and edir == 'down' and exit_nbi >= 3:
            third = bi_list[exit_seg['start_bi'] + 2]
            if third['direction'] == 'down':
                rebound_bi = bi_list[exit_seg['start_bi'] + 1]
                rebound_hi = max(rebound_bi['start_price'], rebound_bi['end_price'])
                if rebound_hi < zd:
                    entry_f = macd_sum(entry_seg['start_bi'], entry_seg['end_bi'])
                    exit_f = macd_sum(exit_seg['start_bi'], exit_seg['end_bi'])
                    if exit_f < entry_f * 0.7:
                        bb = find_bottom_bi(exit_seg['start_bi'], exit_seg['end_bi'])
                        if bb and bb[1] < zd:
                            add_sig('1B', i, exit_idx, bb[1]); has['1B'][i] = True

        # ===== S2: 上涨趋势第二个中枢→新高即卖 =====
        if edir == 'up' and prev_i is not None and not has['S2'].get(i):
            tb = find_top_bi(exit_seg['start_bi'], exit_seg['end_bi'])
            if tb and tb[1] > zg:
                add_sig('S2', i, exit_idx, tb[1]); has['S2'][i] = True

        # ===== 1C: 趋势背驰卖点 =====
        if edir == 'up' and exit_nbi >= 1:
            ok = True
            if exit_nbi >= 3:
                third = bi_list[exit_seg['start_bi'] + 2]
                if third['direction'] != 'up': ok = False
            if ok:
                entry_f = macd_sum(entry_seg['start_bi'], entry_seg['end_bi'])
                exit_f = macd_sum(exit_seg['start_bi'], exit_seg['end_bi'])
                if exit_f < entry_f * 1.5:
                    tb = find_top_bi(exit_seg['start_bi'], exit_seg['end_bi'])
                    if tb and tb[1] > zg:
                        add_sig('1C', i, exit_idx, tb[1]); has['1C'][i] = True

        # ===== P1C: 盘整背驰卖点(单上涨中枢) =====
        if edir == 'up' and prev_i is None and exit_nbi >= 3:
            third = bi_list[exit_seg['start_bi'] + 2]
            if third['direction'] == 'up':
                zs_best_macd = 0.0
                for k in range(ss, es + 1):
                    sm = macd_sum(segments[k]['start_bi'], segments[k]['end_bi'])
                    if sm > zs_best_macd: zs_best_macd = sm
                exit_f = macd_sum(exit_seg['start_bi'], exit_seg['end_bi'])
                if zs_best_macd > 0 and exit_f < zs_best_macd * 0.9:
                    tb = find_top_bi(exit_seg['start_bi'], exit_seg['end_bi'])
                    if tb and tb[1] > zg:
                        add_sig('P1C', i, exit_idx, tb[1])
                        if 'P1C' not in has: has['P1C'] = {}
                        has['P1C'][i] = True

        # ===== 2B: 二买 =====
        if not in_expansion and edir == 'down' and not has['2B'].get(i):
            ref_low = None
            if has['1B'].get(i):
                for sig in signals:
                    if sig['type'] == '1B': ref_low = sig['price']; break
            if ref_low is None: ref_low = seg_lo(exit_seg)

            rebound_idx = None
            for bidx in range(exit_seg['end_bi'] + 1, len(bi_list)):
                if bi_list[bidx]['direction'] == 'up': rebound_idx = bidx; break
            if rebound_idx is not None:
                rebound_hi = max(bi_list[rebound_idx]['start_price'], bi_list[rebound_idx]['end_price'])
                if rebound_hi < zd:
                    down_count = 0; down_seq_end = rebound_idx
                    for bidx in range(rebound_idx + 1, len(bi_list)):
                        if bi_list[bidx]['direction'] == 'down': down_count += 1
                        down_seq_end = bidx
                        if down_count >= 3: break
                    if down_count >= 3:
                        seq_low = float('inf'); lowest_bi = rebound_idx + 1
                        for bidx in range(rebound_idx + 1, down_seq_end + 1):
                            b = bi_list[bidx]; lo = min(b['start_price'], b['end_price'])
                            if lo < seq_low: seq_low = lo; lowest_bi = bidx
                        if seq_low > ref_low:
                            seq_macd = macd_sum(rebound_idx + 1, down_seq_end)
                            exit_macd_2b = macd_sum(exit_seg['start_bi'], exit_seg['end_bi'])
                            if seq_macd < exit_macd_2b * 0.7:
                                if bi_list[lowest_bi]['end_price'] < zd:
                                    bb = find_bottom_bi(rebound_idx + 1, down_seq_end)
                                    if bb: add_sig('2B', i, exit_idx, bb[1]); has['2B'][i] = True

        # ===== 2C: 二卖 =====
        if edir == 'up' and not has['2C'].get(i):
            ref_high = None
            if has['1C'].get(i):
                for sig in signals:
                    if sig['type'] == '1C': ref_high = sig['price']; break
            if ref_high is None: ref_high = seg_hi(exit_seg)

            found_2c = False
            for j in range(exit_idx + 1, len(segments)):
                if found_2c: break
                s = segments[j]
                if s['dir'] == 'up': continue
                for k in range(j + 1, len(segments)):
                    if found_2c: break
                    sk = segments[k]
                    if sk['dir'] != 'up': continue
                    sh = seg_hi(sk)
                    if sh < ref_high:
                        tb = find_top_bi(sk['start_bi'], sk['end_bi'])
                        if tb:
                            add_sig('2C', i, k, tb[1]); has['2C'][i] = True; found_2c = True

        # ===== 3B: 三买 =====
        _prev_entry_dir = None
        for _ci in range(i - 1, -1, -1):
            _pc = acs[_ci]
            if _pc['ZG'] <= _pc['ZD']: continue
            _pss = bi_to_seg.get(_pc['start_bi'])
            if _pss is None: continue
            _pentry = segments[_pss - 1] if _pss > 0 else segments[_pss]
            _prev_entry_dir = _pentry.get('dir', '')
            break

        if not in_expansion and edir == 'up' and _prev_entry_dir == 'down' and not has['3B'].get(i):
            for j in range(exit_idx + 1, len(segments)):
                s = segments[j]
                if s['dir'] == 'up': continue
                if seg_lo(s) >= zg:
                    bb = find_bottom_bi(s['start_bi'], s['end_bi'])
                    if bb:
                        bi_amp = abs(bi_list[bb[0]]['end_price'] - bi_list[bb[0]]['start_price']) / bb[1] if bb[1] > 0 else 0
                        if bi_amp <= 0.35:
                            add_sig('3B', i, j, bb[1]); has['3B'][i] = True
                break

        # ===== 3C: 三卖 =====
        if not in_expansion and edir == 'down' and _prev_entry_dir == 'up' and not has['3C'].get(i):
            for j in range(exit_idx + 1, len(segments)):
                s = segments[j]
                if s['dir'] == 'down': continue
                if seg_hi(s) <= zd:
                    tb = find_top_bi(s['start_bi'], s['end_bi'])
                    if tb: add_sig('3C', i, j, tb[1]); has['3C'][i] = True
                break

    seen = set(); unique = []
    for s in signals:
        key = (s['type'], s['direction'], s['idx'])
        if key not in seen: seen.add(key); unique.append(s)
    unique.sort(key=lambda s: s['idx'])
    return unique


# ============================================================
# 通用数据加载 (开放接口; 不依赖任何本地数据库)
# ============================================================
def _db_row_ok(r):
    """库行校验: 日期=YYYYMMDD / OHLC 全为正 (指数脏行事故防线, 不设价格上限)。"""
    d = r[0]
    if len(d) != 8:
        return False
    try:
        y, m, dd = int(d[:4]), int(d[4:6]), int(d[6:8])
        if not (1000 < y < 2100 and 1 <= m <= 12 and 1 <= dd <= 31):
            return False
    except ValueError:
        return False
    return r[1] > 0 and r[2] > 0 and r[3] > 0 and r[4] > 0


def _norm_item(r, fields=None):
    """单条记录 → (YYYYMMDD, o, h, l, c, v); 非法返回 None。
    支持: dict(date/open/high/low/close/volume) 或序列 (date,o,h,l,c,v)。
    日期: YYYYMMDD / YYYY-MM-DD(自动转) 两种主流格式。"""
    if isinstance(r, dict):
        # fields 约定 {原始列名: 标准名}, 如 {'trade_date': 'date', 'vol': 'volume'}
        def g(k, d=None, _r=r, _f=fields):
            if _f:
                col = next((c for c, t in _f.items() if t == k), None)
                return _r.get(col, d) if col else d
            return _r.get(k, d)
        raw = (g('date'), g('open'), g('high'), g('low'), g('close'), g('volume'))
    else:
        raw = tuple(r[:6])
        if len(raw) < 6:
            return None
    date = str(raw[0] or '')
    digits = ''.join(ch for ch in date if ch.isdigit())
    if len(digits) >= 8:
        date = digits[:8]
    try:  # 只包转换: 校验须在 try 外 — _db_row_ok 内部比较抛 TypeError 会被 except 误吞
        vals = tuple(float(x) for x in raw[1:6])
    except (TypeError, ValueError):
        return None
    rec = (date,) + vals
    return rec if _db_row_ok(rec) else None


def _normalize_records(records, fields=None):
    """通用记录规范化: 校验(_db_row_ok 同款) + 按日期排序; 返回 dict 行列表=引擎 data 格式。"""
    out = []
    for r in records:
        c = _norm_item(r, fields)
        if c:
            out.append({"date": c[0], "open": c[1], "high": c[2], "low": c[3],
                        "close": c[4], "volume": c[5]})
    out.sort(key=lambda x: x["date"])
    return out


def _pick_col(cols, names):
    """CSV 表头匹配: 中文/英文列名 → 字段 (开放数据入口用)。"""
    for n in names:
        for c in cols:
            if c.lower() == n:
                return c
    return None


# ============================================================
# KlineChanlunEngine — 接口兼容封装
# ============================================================
class KlineChanlunEngine:
    """标准缠论引擎 V2 — 开放数据入口 load_records/from_csv; 兼容本地库 load_data。

    出品: jerrypps3-glitch / chanlun-engine (AGPL-3.0-or-later)
    来源标记: 模块级 __origin__ / verify_origin(); 输出数据内嵌 '_src' 字段。
    """

    ORIGIN = __origin__  # 类级来源标记 (身份跟随任何子类/实例)

    def __init__(self, code, db_path=""):
        # db_path 不再内置本机默认值 (生产端显式传参; 开源用户走 load_records/from_csv)
        self.code = code
        self.is_index = code.startswith('sh000') or code.startswith('sz399')
        self.db_path = db_path
        # 公开输出 (兼容旧接口)
        self.data = []
        self.proc_klines = []
        self.bi_list = []
        self.segment_list = []
        self.archived_centers = []
        self.signals = []
        self.macd = []
        self.bi_signals = []
        self.expanded_centers = []
        self.expansion_zones = []
        self.trends = []
        self.trend_structure = {}
        # 内部状态
        self._loaded = False
        self._ran = False
        # 内部中间格式
        self._mk = []       # merged K-lines (our format)
        self._bi = []       # bi (our format)
        self._seg = []      # segments (our format)
        self._zs_bi = []    # bi centers (our format)
        self._zs_seg = []   # seg centers (our format)
        self._bsp_raw = []  # raw BSP signals (our format)

    # ---- 数据加载 ----
    def load_data(self, start_date="2000-01-01"):
        if not self.db_path:
            raise ValueError(
                "未提供 db_path。本地库装载请显式传入 db_path; "
                "开源通用装载请用 load_records(records) 或 KlineChanlunEngine.from_csv(code, path)")
        db = sqlite3.connect(self.db_path)
        # 代码变体: 裸 6 位 → 兼容 sh/sz 前缀 (2026-09-01 修复: 补数后库里只有带前缀格式)
        codes = [self.code]
        if not self.code.startswith(('sh', 'sz', 'SH', 'SZ')):
            codes = [self.code, 'sh' + self.code, 'sz' + self.code]
        ph = ','.join('?' * len(codes))
        if self.is_index:
            table = "index_daily"
        else:
            table = "daily"
        rows = db.execute(
            f"SELECT date, open, high, low, close, volume FROM {table} WHERE code IN ({ph}) AND date>=? ORDER BY date",
            (*codes, start_date)
        ).fetchall()
        # 空数据 fallback: 指数可能在 daily 表, 个股可能在 index_daily
        if not rows and not self.is_index:
            rows = db.execute(
                f"SELECT date, open, high, low, close, volume FROM index_daily WHERE code IN ({ph}) AND date>=? ORDER BY date",
                (*codes, start_date)
            ).fetchall()
            if rows:
                self.is_index = True
        elif not rows and self.is_index:
            rows = db.execute(
                f"SELECT date, open, high, low, close, volume FROM daily WHERE code IN ({ph}) AND date>=? ORDER BY date",
                (*codes, start_date)
            ).fetchall()
        db.close()
        # 源数据校验 (2026-09-01 指数脏数据事故; 2026-09-02 补日期合法性):
        # index_daily 曾混入 pytdx 负值close/amount错位高值/乱码日期行(如'13008343'月份非法)。
        # 只拦"日期非法/负值", 不设价格上限 — 避免把未来牛市新高当脏数据误杀。
        def _row_ok(r):
            d = r[0]
            if len(d) != 8:
                return False
            try:
                y, m, dd = int(d[:4]), int(d[4:6]), int(d[6:8])
                if not (1000 < y < 2100 and 1 <= m <= 12 and 1 <= dd <= 31):
                    return False
            except ValueError:
                return False
            return r[1] > 0 and r[2] > 0 and r[3] > 0 and r[4] > 0
        self.data = [{"date": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
                     for r in rows if _row_ok(r)]
        self._loaded = True
        return self

    # ---- 开放数据入口 (开源用户用这两个; 不依赖本地数据库) ----
    def load_records(self, records, fields=None):
        """从内存记录装载数据 —— 开源通用入口。

        records: 序列的 dict 或序列。
          dict 键(默认) date/open/high/low/close/volume
          date 须 YYYYMMDD 或 YYYY-MM-DD; OHLC 为正数 — 不满足的行被过滤(同库路径防线)
          fields: 可选列名映射 {原始列名: 标准名}, 如 {'trade_date': 'date', 'vol': 'volume'}
        非 dict 行按 (date, open, high, low, close, volume) 位置解析。
        """
        self.data = _normalize_records(records, fields)
        self._loaded = True
        return self

    @classmethod
    def from_csv(cls, code, path_or_buf, fields=None):
        """从 CSV 装载 (stdlib csv, 零第三方依赖)。列名匹配 date/open/high/low/close/volume,
        也认 trade_date/vol; 中文列名(日期/开盘/最高/最低/收盘/成交量)自动映射。"""
        import csv, io
        buf = path_or_buf if hasattr(path_or_buf, "read") else open(path_or_buf, "r",
              encoding="utf-8-sig", newline="")
        try:
            rows = list(csv.DictReader(buf))
            cols = rows[0].keys() if rows else []
            map_ = {}
            # 先映射标准英文列名, 再补中文/别名列 (避免中文列映射覆盖标准列)
            for target, names in (('date', ('date', 'trade_date', '日期')),
                                  ('open', ('open', '开盘')),
                                  ('high', ('high', '最高')),
                                  ('low', ('low', '最低')),
                                  ('close', ('close', '收盘')),
                                  ('volume', ('volume', 'vol', '成交量'))):
                col = _pick_col(cols, names)
                if col:
                    map_[col] = target
            if fields:
                for k, v in fields.items():
                    map_[v] = k
            return cls(code).load_records(rows, map_)
        finally:
            if not hasattr(path_or_buf, "read"):
                buf.close()

    # ---- 包含处理 ----
    def process_kline_inclusion(self):
        if not self.data and not self._loaded: self.load_data()
        self._loaded = True
        candles = [{'time': d['date'], 'high': d['high'], 'low': d['low'], 'close': d['close']}
                   for d in self.data]
        # 初始方向: 用前两根非包含K线判定
        init_dir = None
        for i in range(1, min(10, len(candles))):
            if candles[i]['high'] > candles[i-1]['high'] and candles[i]['low'] > candles[i-1]['low']:
                init_dir = 'up'; break
            elif candles[i]['high'] < candles[i-1]['high'] and candles[i]['low'] < candles[i-1]['low']:
                init_dir = 'down'; break
        self._mk = merge_klines(candles, init_dir)
        # 兼容旧格式 proc_klines
        self.proc_klines = []
        data_idx = 0
        for i, m in enumerate(self._mk):
            self.proc_klines.append({
                'idx': i, 'high': m['high'], 'low': m['low'],
                'start_time': m.get('start_time', ''), 'end_time': m.get('end_time', ''),
                'dir': m['dir'], 'n': m.get('n', 1),
                'data_start_idx': data_idx,
            })
            data_idx += m.get('n', 1)
        return self

    # ---- 分型检测 ----
    def find_kline_fenxing(self):
        if not self._mk: self.process_kline_inclusion()
        self._fractals = detect_fractals(self._mk)
        return self

    # ---- 笔 ----
    def build_bi(self):
        if not hasattr(self, '_fractals'): self.find_kline_fenxing()
        self._bi, _ = build_bi(self._mk)
        self._build_bi_list_old()
        return self

    def _build_bi_list_old(self):
        """转换为旧版 bi_list 格式: {from: {idx, type, price, date}, to: {...}}

        idx 对齐原始 data 数组。统一使用合并组末位 (data_start_idx + n - 1)
        确保相邻笔在共享分型处锚定同一根K线，避免端点交叉。
        """
        self.bi_list = []
        for b in self._bi:
            from_type = 'top' if b['direction'] == 'down' else 'bottom'
            to_type = 'bottom' if b['direction'] == 'down' else 'top'
            from_idx = b['start_mk']
            to_idx = b['end_mk']
            from_date = to_date = ''
            if b['start_mk'] < len(self.proc_klines):
                pk = self.proc_klines[b['start_mk']]
                from_date = pk.get('start_time', '')
                n = pk.get('n', 1)
                from_idx = pk.get('data_start_idx', b['start_mk']) + n - 1
            if b['end_mk'] < len(self.proc_klines):
                pk = self.proc_klines[b['end_mk']]
                to_date = pk.get('end_time', '')
                n = pk.get('n', 1)
                to_idx = pk.get('data_start_idx', b['end_mk']) + n - 1
            self.bi_list.append({
                'from': {'idx': from_idx, 'type': from_type, 'price': b['start_price'], 'date': from_date},
                'to': {'idx': to_idx, 'type': to_type, 'price': b['end_price'], 'date': to_date},
            })
        return self

    # ---- 段 ----
    def build_segments(self):
        if not self._bi: self.build_bi()
        self._seg = build_segments(self._bi)
        self._build_segment_list_old()
        return self

    def _build_segment_list_old(self):
        """转换为旧版 segment_list 格式: {from, to, direction, start_price, end_price, ...}"""
        self.segment_list = []
        for s in self._seg:
            b0 = self._bi[s['start_bi']]
            b1 = self._bi[s['end_bi']]
            self.segment_list.append({
                'from': s['start_bi'],
                'to': s['end_bi'],
                'direction': s['dir'],
                'start_price': b0['start_price'],
                'end_price': b1['end_price'],
                'sure': s.get('sure', True),  # 透传确认态给前端/导出 (2026-09-02)
            })

    # ---- 中枢 ----
    def build_zhongshu(self):
        if not self._bi: self.build_bi()
        if not self._seg: self.build_segments()

        # 笔中枢
        self._zs_bi = build_zhongshu_bi(self._bi)

        # 段中枢: 给 seg 补起止价
        zs_seg_items = []
        for s in self._seg:
            b0 = self._bi[s['start_bi']]
            b1 = self._bi[s['end_bi']]
            zs_seg_items.append({
                'start_price': b0['start_price'],
                'end_price': b1['end_price'],
                'sure': s.get('sure', True),  # 末段未确认不得入中枢 (2026-09-02)
            })
        self._zs_seg = build_zhongshu_seg(zs_seg_items)

        # 给 seg 补起止价 (BSP detect_bsp_seg 需要)
        for s in self._seg:
            if 'start_price' not in s:
                s['start_price'] = self._bi[s['start_bi']]['start_price']
            if 'end_price' not in s:
                s['end_price'] = self._bi[s['end_bi']]['end_price']

        # bi→seg 映射
        bi_to_seg = {}
        for si, s in enumerate(self._seg):
            for bidx in range(s['start_bi'], s['end_bi'] + 1):
                bi_to_seg[bidx] = si

        # 笔中枢 → 旧格式 archived_centers
        self.archived_centers = []
        for c in self._zs_bi:
            ss = bi_to_seg.get(c['start_bi'])
            es = bi_to_seg.get(c['end_bi'])
            entry_dir = ''
            if ss is not None and ss > 0:
                entry_dir = self._seg[ss-1]['dir']
            elif ss is not None:
                entry_dir = self._seg[ss]['dir']
            self.archived_centers.append({
                'low': c['ZD'], 'high': c['ZG'],
                'dd': c.get('DD', c['ZD']), 'gg': c.get('GG', c['ZG']),
                'startBiIdx': c['start_bi'], 'endBiIdx': c['end_bi'],
                'start_k': self.bi_list[c['start_bi']]['from']['idx'] if c['start_bi'] < len(self.bi_list) else 0,
                'end_k': self.bi_list[c['end_bi']]['to']['idx'] if c['end_bi'] < len(self.bi_list) else 0,
                'startSegIdx': ss if ss is not None else 0,
                'endSegIdx': es if es is not None else 0,
                'total_segs': (es - ss + 1) if (ss is not None and es is not None) else 3,
                'direction': entry_dir,
                'level': 'standard',
            })

        # 段中枢 → 扩展段中枢 (兼容旧 expanded_centers)
        self.seg_archived_centers = []
        seg_to_seg = {}
        for si, s in enumerate(self._seg):
            seg_to_seg[si] = si

        for c in self._zs_seg:
            seg_start = c.get('start_seg', 0)
            seg_end = c.get('end_seg', 0)
            entry_dir = ''
            if seg_start > 0 and seg_start < len(self._seg):
                entry_dir = self._seg[seg_start-1]['dir']
            self.seg_archived_centers.append({
                'low': c['ZD'], 'high': c['ZG'],
                'dd': c.get('DD', c['ZD']), 'gg': c.get('GG', c['ZG']),
                'startSegIdx': seg_start, 'endSegIdx': seg_end,
                'total_segs': seg_end - seg_start + 1,
                'direction': entry_dir, 'level': 'standard',
            })

        self.bi_archived_centers = self.archived_centers
        return self

    # ---- 扩张合并 ----
    def merge_expanded_centers(self):
        """合并重叠中枢→高级别"""
        acs = self.archived_centers
        if len(acs) < 2:
            self.expanded_centers = [dict(c) for c in acs]
            self.expansion_zones = []
            return self

        merged = [dict(acs[0])]
        exp_start = None; exp_h = 0; exp_low = float('inf')
        self.expansion_zones = []

        for i, curr in enumerate(acs[1:], 1):
            prev = merged[-1]
            if curr['low'] <= prev['high'] and curr['high'] >= prev['low']:
                # 重叠→合并
                prev['endSegIdx'] = curr['endSegIdx']
                prev['endBiIdx'] = curr['endBiIdx']
                prev['high'] = max(prev['high'], curr['high'])
                prev['low'] = min(prev['low'], curr['low'])
                prev['gg'] = max(prev.get('gg', prev['high']), curr.get('gg', curr['high']))
                prev['dd'] = min(prev.get('dd', prev['low']), curr.get('dd', curr['low']))
                prev['total_segs'] = prev['endSegIdx'] - prev['startSegIdx'] + 1
                prev['level'] = 'standard' if prev['total_segs'] <= 5 else 'upgraded'
                if exp_start is None:
                    sb = acs[i-1].get('startBiIdx', 0)
                    exp_start = self.bi_list[min(sb, len(self.bi_list)-1)]['from']['date'] if self.bi_list else None
                exp_h = max(exp_h, prev['high'])
                exp_low = min(exp_low, prev['low'])
            else:
                if exp_start is not None:
                    sb = acs[i].get('startBiIdx', 0)
                    exp_end = self.bi_list[min(sb, len(self.bi_list)-1)]['from']['date'] if self.bi_list else None
                    self.expansion_zones.append((exp_start, exp_end, exp_h, exp_low))
                    exp_start = None; exp_h = 0; exp_low = float('inf')
                merged.append(dict(curr))

        if exp_start is not None:
            self.expansion_zones.append((exp_start, None, exp_h, exp_low))
        self.expanded_centers = merged
        return self

    # ---- MACD ----
    def calc_macd(self, fast=12, slow=26, signal=9):
        if not self.data:
            self.macd = []
            return self
        closes = [d['close'] for d in self.data]
        dif, dea, macd_hist = calc_macd_raw(closes, fast, slow, signal)
        self.macd = [{'dif': dif[i], 'dea': dea[i], 'macd': macd_hist[i]} for i in range(len(closes))]
        return self

    # ---- BSP 买卖点 ----
    def detect_signals(self):
        if not self._seg: self.build_segments()
        if not self._zs_bi: self.build_zhongshu()
        if not self.macd: self.calc_macd()

        # 段级BSP
        raw = detect_bsp_seg(self._bi, self._seg, self._zs_bi, self._zs_seg, self.data)

        # 转换为旧格式
        self._bsp_raw = raw
        self.signals = []
        buy_types = {'1B', '2B', '3B'}
        pending_buys = []
        for s in raw:
            seg_idx = s['idx']
            # biIdx: 取离开段/回踩段末端笔
            bi_idx = 0
            if seg_idx < len(self._seg):
                bi_idx = self._seg[seg_idx]['end_bi']
            # colIdx: 笔末端K线位置
            col_idx = 0
            if bi_idx < len(self.bi_list):
                col_idx = self.bi_list[bi_idx]['to']['idx']

            sig = {'type': s['type'], 'price': s['price'],
                   'biIdx': bi_idx, 'colIdx': col_idx,
                   'centerIdx': 0, 'paired': False, 'pnl': None}

            t = s['type']
            if t in buy_types:
                pending_buys.append(sig)
            elif t in ('1C', '2C', '3C', 'S2', 'P1C'):
                matched = pending_buys.pop(0) if pending_buys else None
                if matched:
                    matched['paired'] = True; sig['paired'] = True
                    if matched['price'] and matched['price'] != 0:
                        pnl = (sig['price'] - matched['price']) / matched['price']
                        matched['pnl'] = pnl; sig['pnl'] = pnl
                    self.signals.append(matched)
                else:
                    sig['paired'] = False; sig['pnl'] = None
                self.signals.append(sig)
            else:
                self.signals.append(sig)

        for b in pending_buys:
            b['paired'] = False; b['pnl'] = None
        self.signals.extend(pending_buys)
        self.signals.sort(key=lambda s: s.get('colIdx', 0))

        self.bi_signals = []  # 笔级信号留空 (无消费者直接访问)
        return self

    # ---- 走势分类 ----
    def classify_trend(self):
        """走势类型划分 — 基于中枢位置关系"""
        centers = self.expanded_centers or self.archived_centers
        if len(centers) < 2:
            self.trends = [{'type': '盘整', 'direction': '不明', 'centers': [c for c in centers]}]
            return self

        trends = []
        cluster = [centers[0]]
        cluster_dir = centers[0].get('direction', 'unknown')

        for i in range(1, len(centers)):
            prev = centers[i-1]
            curr = centers[i]
            curr_dir = curr.get('direction', 'unknown')

            if curr['low'] > prev['high'] and curr_dir == cluster_dir:
                cluster.append(curr)
            elif curr['high'] < prev['low'] and curr_dir == cluster_dir:
                cluster.append(curr)
            else:
                trend_type = '趋势' if len(cluster) >= 2 else '盘整'
                trends.append({
                    'type': trend_type, 'direction': cluster_dir,
                    'centers': [c for c in cluster],
                    'startBiIdx': cluster[0].get('startBiIdx', 0),
                    'endBiIdx': cluster[-1].get('endBiIdx', 0),
                })
                cluster = [curr]
                cluster_dir = curr_dir

        trend_type = '趋势' if len(cluster) >= 2 else '盘整'
        trends.append({
            'type': trend_type, 'direction': cluster_dir,
            'centers': [c for c in cluster],
            'startBiIdx': cluster[0].get('startBiIdx', 0),
            'endBiIdx': cluster[-1].get('endBiIdx', 0),
        })
        self.trends = trends
        return self

    # ---- 完整管线 ----
    def run(self):
        self.process_kline_inclusion()
        self.find_kline_fenxing()
        self.build_bi()
        self.build_segments()
        self.build_zhongshu()
        self.merge_expanded_centers()
        self.calc_macd()
        self.detect_signals()
        self.classify_trend()
        self._ran = True
        return self

    # ---- 以下为兼容桩 (旧接口有空实现) ----
    def build_high_level(self): return self
    def build_level2_analysis(self): return self
    def build_trends(self): return self.classify_trend()
    def build_bi_zhongshu(self): return self.build_zhongshu()
    def detect_bi_signals(self): return self


# ============================================================
if __name__ == '__main__':
    engine = KlineChanlunEngine("sh600519")
    engine.load_data().calc_macd().run()
    print(f"茅台: {len(engine.bi_list)}笔 {len(engine.segment_list)}段 "
          f"{len(engine.archived_centers)}中枢 {len(engine.signals)}信号")
    for s in engine.signals:
        print(f"  {s['type']} @{s['price']:.2f} paired={s.get('paired')}")
