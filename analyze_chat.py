#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信聊天记录深度分析 - 我和芝芝（改进版）
"""

import sqlite3
import datetime
import re
import math
import os
import base64
from io import BytesIO
from collections import Counter

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.colors import LinearSegmentedColormap
import jieba
from wordcloud import WordCloud
from snownlp import SnowNLP
import emoji

# ─── 配置 ────────────────────────────────────────────────────────────
DB_BASE = "/Volumes/Elements/wechat-decrypt/decrypted/message"
TABLE   = "Msg_4cc83afc7a34bc3d0be5c2213ea0b81d"
OUTPUT  = "/Volumes/Elements/wechat-decrypt/chat_analysis_report.html"
MY_IDS  = {0: 9, 1: 16, 2: 98, 3: 1}
FONT_PATH = "/System/Library/Fonts/PingFang.ttc"

STOPWORDS = set([
    '嗯','哦','啊','的','了','是','在','我','你','他','她','它','们','这','那','有','也',
    '就','都','但','和','与','或','到','从','把','被','让','所','以','如','果','才','已',
    '很','非常','太','更','最','真','好','哈','哈哈','哈哈哈','嘿','诶','唉','呀','吧',
    '呢','呗','哟','哎','哎呀','对','不','没','没有','不是','就是','还是','还有','因为',
    '所以','但是','然后','一个','这个','那个','什么','怎么','为什么','可以','可能',
    '知道','觉得','感觉','一下','一直','一起','现在','今天','明天','昨天','时候',
    '我们','你们','他们','大家','自己','这样','那样','这里','那里','一样','其实',
    '应该','需要','可以','还是','只是','只有','要','会','能','想','说','去','来','看',
    '做','用','给','让','帮','问','回','发','看看','说说','聊','聊聊','哇','wow',
    'ok','OK','Ok','好的','嗯嗯','哦哦','啊啊','嗯嗯嗯','哦哦哦','吗','的话',
    '然后','就是','其实','感觉','觉得','还好','挺','蛮','比较','有点','有些',
    'None','none','null','true','false',
])

# 微信消息类型解码
def decode_msg_type(t):
    """解码微信消息类型，包括 type49 的子类型"""
    base = t % (2**32)
    sub  = t // (2**32)
    if base == 49:
        subtype_names = {
            1: '链接/文章', 5: '链接分享', 6: '文件', 8: '位置共享',
            17: '实时位置', 19: '小程序', 33: '小程序', 36: '小程序',
            40: '音乐', 43: '视频', 51: '视频号', 57: '引用回复',
            62: '视频号直播', 63: '视频号', 87: '群公告',
            2000: '拍一拍', 2003: '拍一拍',
        }
        return subtype_names.get(sub, f'富媒体({sub})')
    base_names = {
        1: '文字', 3: '图片', 34: '语音', 43: '视频',
        47: '表情包', 49: '富媒体', 10000: '系统消息',
        50: '通话', 42: '名片', 48: '位置',
    }
    return base_names.get(base, f'其他({base})')

# ─── 颜色主题 ─────────────────────────────────────────────────────────
PINK  = '#FF6B9D'
BLUE  = '#4A90D9'
GOLD  = '#FFB347'
GREEN = '#52C41A'
PURPLE= '#9B59B6'
BG    = '#FFF8FA'
BG2   = '#F0F4FF'
PALETTE = [PINK, BLUE, GOLD, GREEN, PURPLE, '#E74C3C', '#1ABC9C', '#F39C12']

print("=" * 60)
print("微信聊天记录分析（改进版）...")
print("=" * 60)

# ─── 加载数据 ─────────────────────────────────────────────────────────
records = []
for db_idx in range(4):
    db_path = os.path.join(DB_BASE, f"message_{db_idx}.db")
    my_id = MY_IDS[db_idx]
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"SELECT real_sender_id, create_time, local_type, message_content FROM {TABLE} ORDER BY create_time")
    for row in cur.fetchall():
        sender_id, ts, msg_type, content = row
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')
        records.append({
            'sender': 'me' if sender_id == my_id else 'her',
            'timestamp': ts,
            'type': msg_type,
            'content': content or '',
        })
    conn.close()
    print(f"  DB{db_idx} 加载完成")

df = pd.DataFrame(records)
df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
df['date']    = df['datetime'].dt.date
df['hour']    = df['datetime'].dt.hour
df['weekday'] = df['datetime'].dt.weekday
df['month']   = df['datetime'].dt.to_period('M')
df = df.drop_duplicates(subset=['timestamp', 'sender', 'content'])
df = df.sort_values('datetime').reset_index(drop=True)

text_df = df[df['type'] == 1].copy()
text_df['content'] = text_df['content'].astype(str)

total     = len(df)
me_count  = (df['sender'] == 'me').sum()
her_count = (df['sender'] == 'her').sum()
me_pct    = me_count / total * 100
her_pct   = her_count / total * 100
days_span = (df['datetime'].max() - df['datetime'].min()).days

print(f"\n总消息数: {total:,}  跨度: {days_span} 天")

# ─── 工具函数 ─────────────────────────────────────────────────────────
def fig_to_b64(fig):
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')

def setup_font():
    try:
        prop = fm.FontProperties(fname=FONT_PATH)
        plt.rcParams['font.family'] = prop.get_name()
        plt.rcParams['axes.unicode_minus'] = False
        return prop
    except:
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC']
        plt.rcParams['axes.unicode_minus'] = False
        return None

def set_ax_font(ax, fp):
    for item in ax.get_xticklabels() + ax.get_yticklabels():
        item.set_fontproperties(fp)

def clean_ax(ax):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', alpha=0.25, linestyle='--')

font_prop = setup_font()
charts = {}

# ═══════════════════════════════════════════════════════════════════════
# 1. 消息总览 - 图表
# ═══════════════════════════════════════════════════════════════════════
print("\n[1/6] 消息总览...")

# ── 图1a: 消息类型分布（正确解码）──────────────────────────────────────
# 汇总类型，给小类型归入"其他"
type_raw = df['type'].value_counts()
type_labeled = {}
for t, cnt in type_raw.items():
    label = decode_msg_type(int(t))
    type_labeled[label] = type_labeled.get(label, 0) + cnt

# 排序，只展示 top8，其余合并
sorted_types = sorted(type_labeled.items(), key=lambda x: x[1], reverse=True)
top_n = 8
main_types = sorted_types[:top_n]
others_sum = sum(v for _, v in sorted_types[top_n:])
if others_sum > 0:
    main_types.append(('其他', others_sum))

labels_t = [x[0] for x in main_types][::-1]
vals_t   = [x[1] for x in main_types][::-1]

fig, axes = plt.subplots(1, 2, figsize=(14, 5), facecolor=BG)

# 左：饼图
ax1 = axes[0]
ax1.set_facecolor(BG)
pie_labels = [f'我\n{me_count:,}条\n({me_pct:.1f}%)', f'芝芝\n{her_count:,}条\n({her_pct:.1f}%)']
wedges, _ = ax1.pie(
    [me_count, her_count],
    labels=pie_labels, colors=[BLUE, PINK],
    startangle=90,
    textprops={'fontproperties': font_prop, 'fontsize': 11},
    wedgeprops={'edgecolor': 'white', 'linewidth': 3},
    pctdistance=0.8,
)
ax1.set_title('消息发送比例', fontproperties=font_prop, fontsize=13, fontweight='bold', pad=15)

# 右：消息类型水平条形图
ax2 = axes[1]
ax2.set_facecolor(BG)
bar_colors = [PALETTE[i % len(PALETTE)] for i in range(len(labels_t))]
bars = ax2.barh(labels_t, vals_t, color=bar_colors, edgecolor='white', linewidth=0.5, height=0.65)
ax2.set_title('消息类型分布', fontproperties=font_prop, fontsize=13, fontweight='bold')
ax2.set_xlabel('消息数量', fontproperties=font_prop)
set_ax_font(ax2, font_prop)
max_v = max(vals_t) if vals_t else 1
for bar, val in zip(bars, vals_t):
    ax2.text(bar.get_width() + max_v * 0.01, bar.get_y() + bar.get_height() / 2,
             f'{val:,}', va='center', fontproperties=font_prop, fontsize=9)
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
ax2.grid(axis='x', alpha=0.25, linestyle='--')
ax2.set_xlim(0, max_v * 1.18)

plt.tight_layout(pad=2)
charts['overview'] = fig_to_b64(fig)
plt.close()

# ── 图1b: 每月消息量趋势 ───────────────────────────────────────────────
monthly = df.groupby(['month', 'sender']).size().unstack(fill_value=0)
months_str = [str(m) for m in monthly.index]
x = np.arange(len(months_str))

fig, ax = plt.subplots(figsize=(16, 5), facecolor=BG)
ax.set_facecolor(BG)

me_vals_m  = monthly.get('me',  pd.Series(0, index=monthly.index)).values
her_vals_m = monthly.get('her', pd.Series(0, index=monthly.index)).values

ax.fill_between(x, me_vals_m,  alpha=0.15, color=BLUE)
ax.fill_between(x, her_vals_m, alpha=0.15, color=PINK)
ax.plot(x, me_vals_m,  color=BLUE, linewidth=2.5, marker='o', markersize=4, label='我',   zorder=3)
ax.plot(x, her_vals_m, color=PINK, linewidth=2.5, marker='o', markersize=4, label='芝芝', zorder=3)

# 峰值标注
peak_idx = int(np.argmax(me_vals_m + her_vals_m))
ax.annotate(f'消息最多\n{months_str[peak_idx]}',
            xy=(peak_idx, (me_vals_m + her_vals_m)[peak_idx]),
            xytext=(peak_idx + 1.5, (me_vals_m + her_vals_m)[peak_idx] * 0.9),
            fontproperties=font_prop, fontsize=8.5, color='#333',
            arrowprops=dict(arrowstyle='->', color='gray', lw=1.2),
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#FFF3E0', alpha=0.9))

step = max(1, len(months_str) // 14)
ax.set_xticks(x[::step])
ax.set_xticklabels(months_str[::step], rotation=45, ha='right', fontproperties=font_prop, fontsize=9)
set_ax_font(ax, font_prop)
ax.set_title('每月消息量趋势', fontproperties=font_prop, fontsize=14, fontweight='bold')
ax.set_xlabel('月份', fontproperties=font_prop)
ax.set_ylabel('消息数量', fontproperties=font_prop)
ax.legend(prop=font_prop, fontsize=11, framealpha=0.7)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.grid(axis='y', alpha=0.25, linestyle='--')
ax.set_xlim(-0.5, len(x) - 0.5)
plt.tight_layout()
charts['monthly_trend'] = fig_to_b64(fig)
plt.close()

# ── 图1c: 每小时分布 ──────────────────────────────────────────────────
hourly_me  = df[df['sender'] == 'me'].groupby('hour').size()
hourly_her = df[df['sender'] == 'her'].groupby('hour').size()
hours = list(range(24))
hme  = [hourly_me.get(h, 0)  for h in hours]
hher = [hourly_her.get(h, 0) for h in hours]

fig, ax = plt.subplots(figsize=(14, 4.5), facecolor=BG)
ax.set_facecolor(BG)
w = 0.38
xh = np.arange(24)
ax.bar(xh - w/2, hme,  w, label='我',   color=BLUE, alpha=0.82, edgecolor='white')
ax.bar(xh + w/2, hher, w, label='芝芝', color=PINK, alpha=0.82, edgecolor='white')
# 深夜阴影
ax.axvspan(-0.5, 4.5, alpha=0.06, color='#7C4DFF', zorder=0)
ax.text(2, max(max(hme), max(hher)) * 0.93, '深夜', ha='center',
        fontproperties=font_prop, fontsize=9, color='#7C4DFF', style='italic')
ax.set_xticks(hours)
ax.set_xticklabels([f'{h}时' for h in hours], fontproperties=font_prop, fontsize=8.5)
set_ax_font(ax, font_prop)
ax.set_title('每小时消息分布', fontproperties=font_prop, fontsize=14, fontweight='bold')
ax.set_ylabel('消息数量', fontproperties=font_prop)
ax.legend(prop=font_prop)
clean_ax(ax)
plt.tight_layout()
charts['hourly'] = fig_to_b64(fig)
plt.close()

# ── 图1d: 星期 × 小时热力图 ───────────────────────────────────────────
wh = df.groupby(['weekday', 'hour']).size().unstack(fill_value=0)
wh = wh.reindex(index=range(7), columns=range(24), fill_value=0)
days_cn = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

fig, ax = plt.subplots(figsize=(14, 3.5), facecolor=BG)
ax.set_facecolor(BG)
cmap = LinearSegmentedColormap.from_list('roseheat', ['#FFF5F7', '#FF6B9D', '#9C1C4E'])
im = ax.imshow(wh.values, cmap=cmap, aspect='auto', interpolation='nearest')
ax.set_yticks(range(7))
ax.set_yticklabels(days_cn, fontproperties=font_prop, fontsize=10)
ax.set_xticks(range(0, 24, 2))
ax.set_xticklabels([f'{h}时' for h in range(0, 24, 2)], fontproperties=font_prop, fontsize=9)
ax.set_title('聊天时间热力图（星期 × 小时）', fontproperties=font_prop, fontsize=13, fontweight='bold')
cbar = plt.colorbar(im, ax=ax, shrink=0.85, pad=0.02)
cbar.set_label('消息数', fontproperties=font_prop, fontsize=9)
plt.tight_layout()
charts['heatmap'] = fig_to_b64(fig)
plt.close()

# 回复时长
# 向量化计算回复时长
_ds = df.sort_values('datetime').reset_index(drop=True)
_dt = _ds['timestamp'].diff()
_switched = _ds['sender'] != _ds['sender'].shift(1)
_valid = _switched & (_dt > 0) & (_dt < 7200)
_reply_data = pd.DataFrame({'dt': _dt[_valid] / 60, 'sender': _ds.loc[_valid, 'sender']})
reply_me_vals  = _reply_data[_reply_data['sender'] == 'me']['dt'].values
reply_her_vals = _reply_data[_reply_data['sender'] == 'her']['dt'].values
avg_reply_me  = float(np.median(reply_me_vals))  if len(reply_me_vals)  > 0 else 0
avg_reply_her = float(np.median(reply_her_vals)) if len(reply_her_vals) > 0 else 0

# ═══════════════════════════════════════════════════════════════════════
# 2. 词云
# ═══════════════════════════════════════════════════════════════════════
print("\n[2/6] 生成词云...")

def clean_text(text):
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[^一-鿿㐀-䶿\w]', ' ', text)
    return text

def get_word_freq(texts):
    cnt = Counter()
    for text in texts:
        for w in jieba.cut(clean_text(str(text))):
            w = w.strip()
            if len(w) >= 2 and w not in STOPWORDS and not w.isdigit() and not w.startswith('\\'):
                cnt[w] += 1
    return cnt

me_texts  = text_df[text_df['sender'] == 'me']['content'].tolist()
her_texts = text_df[text_df['sender'] == 'her']['content'].tolist()
print(f"  文字消息 → 我: {len(me_texts):,}  芝芝: {len(her_texts):,}")

me_wf  = get_word_freq(me_texts)
her_wf = get_word_freq(her_texts)

def make_wc(wf, colormap, title):
    wc = WordCloud(
        font_path=FONT_PATH, width=900, height=420,
        background_color='white', colormap=colormap,
        max_words=160, prefer_horizontal=0.75, min_font_size=10,
    ).generate_from_frequencies(dict(wf.most_common(200)))
    fig, ax = plt.subplots(figsize=(11, 5), facecolor='white')
    ax.imshow(wc, interpolation='bilinear')
    ax.axis('off')
    ax.set_title(title, fontproperties=font_prop, fontsize=14, fontweight='bold', pad=12)
    return fig

charts['wc_me']  = fig_to_b64(make_wc(me_wf,  'Blues',  '我的高频词云'))
charts['wc_her'] = fig_to_b64(make_wc(her_wf, 'RdPu',   '芝芝的高频词云'))
plt.close('all')

# ═══════════════════════════════════════════════════════════════════════
# 3. 情感分析
# ═══════════════════════════════════════════════════════════════════════
print("\n[3/6] 情感分析...")

def sentiment_score(texts, n=80):
    scores = []
    sample = texts[:n] if len(texts) > n else texts
    for t in sample:
        t = clean_text(str(t))
        if len(t) < 2:
            continue
        try:
            scores.append(SnowNLP(t).sentiments)
        except:
            pass
    return float(np.mean(scores)) if scores else 0.5

monthly_sent = {}
monthly_total = df.groupby('month').size()
for month, grp in text_df.groupby('month'):
    ms = str(month)
    me_g  = grp[grp['sender'] == 'me']['content'].tolist()
    her_g = grp[grp['sender'] == 'her']['content'].tolist()
    monthly_sent[ms] = {
        'me':  sentiment_score(me_g),
        'her': sentiment_score(her_g),
        'avg': sentiment_score(me_g + her_g),
    }

months_sorted = sorted(monthly_sent.keys())
sent_me  = [monthly_sent[m]['me']  for m in months_sorted]
sent_her = [monthly_sent[m]['her'] for m in months_sorted]
sent_avg = [monthly_sent[m]['avg'] for m in months_sorted]

best_idx  = int(np.argmax(sent_avg))  if sent_avg else 0
worst_idx = int(np.argmin(sent_avg)) if sent_avg else 0
best_month  = months_sorted[best_idx]  if months_sorted else '—'
worst_month = months_sorted[worst_idx] if months_sorted else '—'

fig, ax = plt.subplots(figsize=(16, 5), facecolor=BG)
ax.set_facecolor(BG)
xs = np.arange(len(months_sorted))
ax.fill_between(xs, 0.5, sent_avg,
                where=[s >= 0.5 for s in sent_avg], alpha=0.12, color=GREEN,   interpolate=True)
ax.fill_between(xs, 0.5, sent_avg,
                where=[s <  0.5 for s in sent_avg], alpha=0.12, color='#E74C3C', interpolate=True)
ax.plot(xs, sent_me,  color=BLUE, linewidth=2,   label='我',   marker='o', markersize=3, zorder=3)
ax.plot(xs, sent_her, color=PINK, linewidth=2,   label='芝芝', marker='o', markersize=3, zorder=3)
ax.plot(xs, sent_avg, color='#888', linewidth=1.2, linestyle='--', label='综合', zorder=2)
ax.axhline(0.5, color='#ccc', linewidth=1, linestyle=':')

# 标注高峰/低谷
if months_sorted:
    ax.axvline(best_idx,  color=GOLD,   linewidth=1.5, linestyle=':', alpha=0.9)
    ax.text(best_idx, 0.96, f'情感高峰\n{best_month}',
            ha='center', fontproperties=font_prop, fontsize=8, color='darkorange',
            va='top', bbox=dict(boxstyle='round,pad=0.3', fc='#FFF3E0', alpha=0.9))
    ax.axvline(worst_idx, color='#9E9E9E', linewidth=1.5, linestyle=':', alpha=0.9)
    ax.text(worst_idx, 0.04, f'情感低谷\n{worst_month}',
            ha='center', fontproperties=font_prop, fontsize=8, color='#666',
            va='bottom', bbox=dict(boxstyle='round,pad=0.3', fc='#F5F5F5', alpha=0.9))

step = max(1, len(months_sorted) // 14)
ax.set_xticks(xs[::step])
ax.set_xticklabels(months_sorted[::step], rotation=45, ha='right', fontproperties=font_prop, fontsize=9)
set_ax_font(ax, font_prop)
ax.set_ylim(0, 1)
ax.set_title('情感变化趋势（基于 SnowNLP，0=消极 / 1=积极）',
             fontproperties=font_prop, fontsize=14, fontweight='bold')
ax.set_ylabel('情感得分', fontproperties=font_prop)
ax.legend(prop=font_prop, framealpha=0.7)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.grid(axis='y', alpha=0.2, linestyle='--')
plt.tight_layout()
charts['sentiment'] = fig_to_b64(fig)
plt.close()

# 情感词统计
pos_words = ['爱','喜欢','开心','快乐','好玩','甜','幸福','棒','厉害','哈哈','嘻嘻','宝','宝宝','哥哥','好看','可爱','萌','赞','完美','温柔']
neg_words = ['难过','委屈','哭','难受','烦','累','气','怒','失望','痛','冷','吵','后悔','郁闷','糟糕','崩溃','心疼','抱歉','对不起']
all_text_joined = ' '.join(text_df['content'].tolist())
pos_cnt = {w: all_text_joined.count(w) for w in pos_words if all_text_joined.count(w) > 0}
neg_cnt = {w: all_text_joined.count(w) for w in neg_words if all_text_joined.count(w) > 0}

fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), facecolor=BG)
for ax_, data, color, title in [
    (axes[0], pos_cnt, PINK, '正面情感词频'),
    (axes[1], neg_cnt, PURPLE, '负面情感词频'),
]:
    ax_.set_facecolor(BG)
    if data:
        items = sorted(data.items(), key=lambda x: x[1], reverse=True)[:12]
        names = [i[0] for i in items][::-1]
        vals  = [i[1] for i in items][::-1]
        bars_ = ax_.barh(names, vals, color=color, alpha=0.82, edgecolor='white', height=0.65)
        for bar, v in zip(bars_, vals):
            ax_.text(bar.get_width() + max(vals)*0.01, bar.get_y()+bar.get_height()/2,
                     f'{v}', va='center', fontproperties=font_prop, fontsize=8.5)
        ax_.set_xlim(0, max(vals)*1.2)
    ax_.set_title(title, fontproperties=font_prop, fontsize=12, fontweight='bold')
    set_ax_font(ax_, font_prop)
    ax_.spines['top'].set_visible(False)
    ax_.spines['right'].set_visible(False)
    ax_.grid(axis='x', alpha=0.25, linestyle='--')
plt.tight_layout()
charts['emotion_words'] = fig_to_b64(fig)
plt.close()

# ═══════════════════════════════════════════════════════════════════════
# 4. 常规分析
# ═══════════════════════════════════════════════════════════════════════
print("\n[4/6] 常规分析...")

# Top10 天
daily_counts = df.groupby('date').size()
top10 = daily_counts.nlargest(10)

fig, ax = plt.subplots(figsize=(13, 5), facecolor=BG)
ax.set_facecolor(BG)
d_str = [str(d) for d in top10.index]
bar_c = [PINK, BLUE, GOLD] + [PALETTE[(i+3) % len(PALETTE)] for i in range(len(d_str) - 3)]
bars = ax.bar(range(len(d_str)), top10.values, color=bar_c, edgecolor='white', linewidth=0.5)
ax.set_xticks(range(len(d_str)))
ax.set_xticklabels(d_str, rotation=35, ha='right', fontproperties=font_prop, fontsize=10)
for bar, v in zip(bars, top10.values):
    ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+5, f'{v}',
            ha='center', va='bottom', fontproperties=font_prop, fontsize=10, fontweight='bold')
ax.set_title('发消息最多的日子 Top 10', fontproperties=font_prop, fontsize=14, fontweight='bold')
ax.set_ylabel('消息数量', fontproperties=font_prop)
set_ax_font(ax, font_prop)
clean_ax(ax)
plt.tight_layout()
charts['top10'] = fig_to_b64(fig)
plt.close()

# 消息长度 + 表情统计
me_len  = text_df[text_df['sender'] == 'me']['content'].str.len()
her_len = text_df[text_df['sender'] == 'her']['content'].str.len()

emoji_pattern = re.compile(r'\[([^\[\]]{1,12})\]')
all_emojis = []
for text in text_df['content']:
    all_emojis.extend(emoji_pattern.findall(str(text)))
emoji_cnt = Counter(all_emojis)
top_emojis = emoji_cnt.most_common(15)

fig, axes = plt.subplots(1, 2, figsize=(14, 5), facecolor=BG)

# 消息长度分布
ax1 = axes[0]
ax1.set_facecolor(BG)
clip = 150
ax1.hist(me_len[me_len <= clip],  bins=40, alpha=0.65, color=BLUE, label=f'我 (中位{me_len.median():.0f}字)',  density=True)
ax1.hist(her_len[her_len <= clip], bins=40, alpha=0.65, color=PINK, label=f'芝芝 (中位{her_len.median():.0f}字)', density=True)
ax1.set_title('消息长度分布', fontproperties=font_prop, fontsize=12, fontweight='bold')
ax1.set_xlabel('字数（截断至150字）', fontproperties=font_prop)
ax1.set_ylabel('概率密度', fontproperties=font_prop)
ax1.legend(prop=font_prop)
set_ax_font(ax1, font_prop)
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)

# 表情排行
ax2 = axes[1]
ax2.set_facecolor(BG)
if top_emojis:
    e_names = [f'[{e[0]}]' for e in top_emojis[:12]][::-1]
    e_vals  = [e[1] for e in top_emojis[:12]][::-1]
    bars2 = ax2.barh(e_names, e_vals,
                     color=[PINK if i%2==0 else BLUE for i in range(len(e_names))],
                     edgecolor='white', height=0.65)
    for bar, v in zip(bars2, e_vals):
        ax2.text(bar.get_width()+max(e_vals)*0.01, bar.get_y()+bar.get_height()/2,
                 f'{v}', va='center', fontproperties=font_prop, fontsize=9)
    ax2.set_xlim(0, max(e_vals)*1.18)
ax2.set_title('最常用微信表情 Top12', fontproperties=font_prop, fontsize=12, fontweight='bold')
ax2.set_xlabel('使用次数', fontproperties=font_prop)
set_ax_font(ax2, font_prop)
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
ax2.grid(axis='x', alpha=0.25, linestyle='--')
plt.tight_layout()
charts['len_emoji'] = fig_to_b64(fig)
plt.close()

# 主动发起对话
print("  分析主动发起对话...")
initiate_me = initiate_her = 0
prev_ts = prev_sender = None
for _, row in df.iterrows():
    if prev_ts is None or (row['timestamp'] - prev_ts > 3600):
        if row['sender'] == 'me': initiate_me += 1
        else: initiate_her += 1
    prev_ts = row['timestamp']
    prev_sender = row['sender']

# 深夜统计
late_night = df[df['hour'].isin([0,1,2,3,4])]
late_count = len(late_night)
late_days  = late_night.groupby('date').size().nlargest(3)

# 最长连续聊天
dates_list = sorted(set(daily_counts.index))
max_streak = cur_streak = 1
best_start = best_end = dates_list[0] if dates_list else None
for i in range(1, len(dates_list)):
    if (dates_list[i] - dates_list[i-1]).days == 1:
        cur_streak += 1
        if cur_streak > max_streak:
            max_streak = cur_streak
            best_end   = dates_list[i]
            best_start = dates_list[i - cur_streak + 1]
    else:
        cur_streak = 1

# 综合对比雷达图
categories = ['消息数量', '消息长度', '主动发起', '深夜聊天', '回复速度']
me_raw  = [me_count,           me_len.mean(),    initiate_me,  late_night[late_night['sender']=='me'].shape[0],  1/(avg_reply_me+0.1)]
her_raw = [her_count,          her_len.mean(),   initiate_her, late_night[late_night['sender']=='her'].shape[0], 1/(avg_reply_her+0.1)]
# 归一化
def norm(a, b):
    tot = a + b
    return (a/tot*100, b/tot*100) if tot > 0 else (50, 50)

pairs = [norm(m, h) for m, h in zip(me_raw, her_raw)]
me_norm  = [p[0] for p in pairs]
her_norm = [p[1] for p in pairs]

N = len(categories)
angles = [n/N*2*math.pi for n in range(N)] + [0]
me_n_c  = me_norm  + [me_norm[0]]
her_n_c = her_norm + [her_norm[0]]

fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True), facecolor=BG)
ax.set_facecolor(BG)
ax.plot(angles, me_n_c,  color=BLUE, linewidth=2, label='我')
ax.fill(angles, me_n_c,  color=BLUE, alpha=0.18)
ax.plot(angles, her_n_c, color=PINK, linewidth=2, label='芝芝')
ax.fill(angles, her_n_c, color=PINK, alpha=0.18)
ax.set_xticks(angles[:-1])
ax.set_xticklabels(categories, fontproperties=font_prop, fontsize=11)
ax.set_yticks([25, 50, 75])
ax.set_yticklabels(['25%', '50%', '75%'], fontproperties=font_prop, fontsize=8)
ax.set_ylim(0, 100)
ax.set_title('我 vs 芝芝 各项对比', fontproperties=font_prop, fontsize=13, fontweight='bold', pad=25)
ax.legend(prop=font_prop, loc='upper right', bbox_to_anchor=(1.3, 1.1))
plt.tight_layout()
charts['radar'] = fig_to_b64(fig)
plt.close()

# ═══════════════════════════════════════════════════════════════════════
# 5. 深度分析数据准备
# ═══════════════════════════════════════════════════════════════════════
print("\n[5/6] 深度分析...")

def get_msgs(start_dt=None, end_dt=None, n=120):
    mask = pd.Series([True] * len(text_df), index=text_df.index)
    if start_dt: mask = mask & (text_df['datetime'] >= start_dt)
    if end_dt:   mask = mask & (text_df['datetime'] <= end_dt)
    sub = text_df[mask]
    if len(sub) > n:
        sub = sub.sample(n, random_state=42).sort_values('datetime')
    msgs = []
    for _, row in sub.iterrows():
        lbl = '我' if row['sender'] == 'me' else '芝芝'
        msgs.append((lbl, str(row['content'])))
    return msgs

early_msgs = get_msgs(pd.Timestamp('2022-08-19'), pd.Timestamp('2022-08-25'), n=50)

peak_month_period = monthly_total.idxmax()
peak_month_str = str(peak_month_period)
peak_msgs = get_msgs(pd.Timestamp(peak_month_str+'-01'),
                     pd.Timestamp(peak_month_str+'-01') + pd.offsets.MonthEnd(1), n=100)

recent_msgs = get_msgs(pd.Timestamp('2026-01-01'), n=120)

# 称谓词统计
endear_words = ['宝宝','宝','哥哥','老婆','老公','亲爱','傻瓜','猪猪','小猪','笨蛋']
endear_cnt = {w: all_text_joined.count(w) for w in endear_words if all_text_joined.count(w) > 0}
top_endear = sorted(endear_cnt.items(), key=lambda x: x[1], reverse=True)[:4]
endear_str = '、'.join([f'"{w}"({c}次)' for w, c in top_endear]) if top_endear else '无明显固定称谓'

# 话题分析
topic_map = {
    '吃饭/美食': ['吃','饭','饿','好吃','餐厅','外卖','点餐','奶茶','咖啡'],
    '睡觉/休息': ['睡','困','起床','早安','晚安','休息','觉'],
    '学习/工作': ['作业','考试','上班','下班','实习','项目','报告','论文','学习'],
    '游戏/娱乐': ['游戏','剧','电影','综艺','音乐','演唱会','追剧'],
    '约会/出行': ['出去','逛','旅游','约','见面','来找','散步'],
    '情感表达':  ['爱','喜欢','想你','思念','爱你','心疼','开心'],
}
topic_totals = {}
for topic, kws in topic_map.items():
    topic_totals[topic] = sum(all_text_joined.count(kw) for kw in kws)
top_topics_sorted = sorted(topic_totals.items(), key=lambda x: x[1], reverse=True)
total_topic = sum(topic_totals.values()) or 1
topics_str = '、'.join([f'{t}({v/total_topic*100:.0f}%)' for t, v in top_topics_sorted[:3]])

# 冷战检测（消息量骤降）
monthly_vals_list = [(str(m), v) for m, v in monthly_total.items()]
monthly_mean = monthly_total.mean()
cold_periods = []
for i in range(1, len(monthly_vals_list)):
    prev_v = monthly_vals_list[i-1][1]
    curr_m, curr_v = monthly_vals_list[i]
    if curr_v < prev_v * 0.5 and curr_v < monthly_mean * 0.65:
        cold_periods.append(curr_m)

# 话题雷达图
cats = list(topic_map.keys())
topic_vals_norm = [topic_totals[c]/max(topic_totals.values()) for c in cats]
N2 = len(cats)
angles2 = [n/N2*2*math.pi for n in range(N2)] + [0]
vals_r = topic_vals_norm + [topic_vals_norm[0]]

fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True), facecolor=BG)
ax.set_facecolor(BG)
ax.plot(angles2, vals_r, color=PINK, linewidth=2.5)
ax.fill(angles2, vals_r, color=PINK, alpha=0.22)
ax.set_xticks(angles2[:-1])
ax.set_xticklabels(cats, fontproperties=font_prop, fontsize=10.5)
ax.set_yticks([0.25, 0.5, 0.75, 1.0])
ax.set_yticklabels(['', '', '', ''], fontsize=8)
ax.set_title('聊天话题分布', fontproperties=font_prop, fontsize=13, fontweight='bold', pad=25)
plt.tight_layout()
charts['topic_radar'] = fig_to_b64(fig)
plt.close()

# ═══════════════════════════════════════════════════════════════════════
# 构建深度分析文本
# ═══════════════════════════════════════════════════════════════════════
late_rate = late_count / total * 100

if me_len.mean() > her_len.mean() * 1.12:
    talky = f"消息长度来看你更话痨（你均 {me_len.mean():.0f} 字，芝芝均 {her_len.mean():.0f} 字）"
elif her_len.mean() > me_len.mean() * 1.12:
    talky = f"消息长度来看芝芝更话痨（芝芝均 {her_len.mean():.0f} 字，你均 {me_len.mean():.0f} 字）"
else:
    talky = f"你们消息长度差不多（你均 {me_len.mean():.0f} 字，芝芝均 {her_len.mean():.0f} 字）"

if initiate_me > initiate_her * 1.15:
    initiative = f"主动发起对话上，你明显更主动（你 {initiate_me:,} 次，芝芝 {initiate_her:,} 次）"
elif initiate_her > initiate_me * 1.15:
    initiative = f"主动发起对话上，芝芝更主动（芝芝 {initiate_her:,} 次，你 {initiate_me:,} 次）"
else:
    initiative = f"主动发起对话上你俩基本持平（你 {initiate_me:,} 次，芝芝 {initiate_her:,} 次）"

if avg_reply_her < avg_reply_me * 0.85:
    reply_comment = "芝芝回复比你快一些，说明她在线时通常更积极。"
elif avg_reply_me < avg_reply_her * 0.85:
    reply_comment = "你回复比芝芝快一些，说明你在聊天时更积极。"
else:
    reply_comment = "你们回复速度旗鼓相当，默契度不错。"

if cold_periods:
    cold_str = f"有几个月消息量明显减少——{', '.join(cold_periods[:3])}——可能是经历了摩擦、各自很忙，或者有段时间见面多了就不怎么发消息了。"
else:
    cold_str = "从消息量曲线来看，没有明显的断崖式冷淡期，这段感情的连续性很好。"

deep_analysis = f"""你们是 2022 年 8 月 19 日认识的。

芝芝先通过了你的好友请求，然后你发了第一句"hihi"。从早期的聊天看，你们大概是同届同学，通过密码互加微信——开口就聊绩点、卷王，是那种初识时互相摸底的感觉。

**感情发展脉络**

刚认识时（2022 年 8-9 月），话题以学校、成绩、共同朋友为主，带着一点点初识的客气。随着时间推移，聊天慢慢从"同学"变成"朋友"，再到后来的更亲密的关系。

消息量在 {peak_month_str} 达到顶峰，那个月平均每天 {int(monthly_total.max()/30)} 条消息——这是感情最热络、联系最密集的时期。整体来说，近四年里你们几乎没有真正断过联系，{total:,} 条消息、日均 {int(total/max(days_span,1))} 条，这个密度说明这段关系在你们的日常生活里占据了相当重要的位置。

**相处模式**

{talky}。{initiative}。{reply_comment}

你们聊得最多的话题是：{topics_str}。吃什么、几点睡、对方在干什么——这些细碎的日常构成了你们关系最扎实的底色。

你们用过的称呼：{endear_str}。

深夜（0-5 点）聊天占总量的 {late_rate:.1f}%——{"这个比例挺高的，说明你们不少对话发生在夜深人静的时候，那种没有时间压力、想说什么就说什么的感觉。" if late_rate > 8 else "算是正常水平，你们大多数时候聊天作息比较规律。"}

**冷战与争吵**

{cold_str}

情感得分最低的月份是 {worst_month}，整体情绪比平时低落。情感最好的时期是 {best_month}，那段时间聊天的氛围明显更轻松、积极。

**两个人的性格**

你——{"发消息偏简洁" if me_len.mean() < 12 else "有时候会多说几句"}，{"在聊天里比较主动" if initiate_me >= initiate_her else "不是那个一直先开口的人"}。从聊天方式猜，你是个话不多、但想说的时候会认真说的人。

芝芝——{"消息也比较精简" if her_len.mean() < 12 else "喜欢多表达几句"}，活泼，表情包用得不少，从早期记录里能看出她是个情绪比较外露、直接的人。"[快哭了]""[大哭]"这类表情她用过很多次，高兴难过都不怎么藏。

**总体评价**

{total:,} 条消息、将近四年——这段感情的"存在感"非常强。从陌生同学走到现在，中间经历了学校、实习、毕业、工作……能一直保持这样的联系密度，说明你们都在认真维系这段关系。

数据层面，互动频繁、话题多元、情感整体偏积极，低谷期有但不长。如果有一点值得注意的话：{"你是更主动的那个，要留意长期下去情感输出是否均衡。" if initiate_me > initiate_her * 1.15 else "你们主动性很均衡，这是个很好的信号——双方都没有在单方面维持这段关系。"}

加油。"""

# ═══════════════════════════════════════════════════════════════════════
# 6. 生成 HTML
# ═══════════════════════════════════════════════════════════════════════
print("\n[6/6] 生成 HTML 报告...")

def img(key, alt=''):
    if key in charts:
        return f'<img src="data:image/png;base64,{charts[key]}" alt="{alt}" style="max-width:100%;border-radius:12px;box-shadow:0 3px 14px rgba(0,0,0,0.09);">'
    return '<p style="color:#bbb;text-align:center">图表未生成</p>'

def chat_bubbles(msg_list, max_n=20):
    html = '<div class="chat-wrap">'
    for lbl, content in msg_list[:max_n]:
        side = 'me' if lbl == '我' else 'her'
        html += f'<div class="crow {side}"><span class="clbl">{lbl}</span><span class="bbl bbl-{side}">{content}</span></div>\n'
    html += '</div>'
    return html

def render_analysis(text):
    lines = text.split('\n')
    parts = []
    for line in lines:
        line = line.strip()
        if not line:
            parts.append('')
        elif line.startswith('**') and line.endswith('**'):
            parts.append(f'<h3 class="section-heading">{line[2:-2]}</h3>')
        else:
            parts.append(f'<p>{line}</p>')
    return '\n'.join(parts)

_analysis_html = render_analysis(deep_analysis)

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>我和芝芝的聊天记录分析 💕</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#FAF5F8;color:#2d2d2d;line-height:1.7}}

/* 顶部 */
.hd{{background:linear-gradient(135deg,#FF6B9D 0%,#C84B8C 60%,#9B59B6 100%);color:#fff;padding:56px 24px 44px;text-align:center;position:relative;overflow:hidden}}
.hd::after{{content:'💕';font-size:200px;position:absolute;right:-30px;bottom:-50px;opacity:.06;pointer-events:none}}
.hd h1{{font-size:2.4em;font-weight:700;letter-spacing:1px;text-shadow:0 2px 12px rgba(0,0,0,.2)}}
.hd p{{margin-top:10px;font-size:1.05em;opacity:.88}}

/* 容器 */
.wrap{{max-width:1080px;margin:0 auto;padding:32px 20px}}

/* 数字卡片 */
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin:30px 0}}
.kpi{{background:#fff;border-radius:16px;padding:22px 16px;text-align:center;box-shadow:0 3px 16px rgba(255,107,157,.1);border-top:4px solid}}
.kpi:nth-child(1){{border-color:#FF6B9D}}
.kpi:nth-child(2){{border-color:#4A90D9}}
.kpi:nth-child(3){{border-color:#FFB347}}
.kpi:nth-child(4){{border-color:#9B59B6}}
.kpi:nth-child(5){{border-color:#52C41A}}
.kpi:nth-child(6){{border-color:#E74C3C}}
.kpi .num{{font-size:1.9em;font-weight:700;color:#FF6B9D;line-height:1.1}}
.kpi .lbl{{font-size:.82em;color:#888;margin-top:6px}}

/* 内容块 */
.sec{{background:#fff;border-radius:20px;padding:36px;margin:24px 0;box-shadow:0 3px 18px rgba(0,0,0,.055)}}
.sec h2{{font-size:1.4em;font-weight:700;padding-bottom:14px;border-bottom:2px solid #FFE4EC;margin-bottom:22px;color:#1a1a1a}}
.sec h2 .ico{{margin-right:8px}}

/* 图表 */
.chart{{margin:20px 0;text-align:center}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:20px 0}}
@media(max-width:700px){{.two{{grid-template-columns:1fr}}}}

/* 人物卡 */
.cards{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:20px 0}}
@media(max-width:600px){{.cards{{grid-template-columns:1fr}}}}
.card{{border-radius:14px;padding:20px;border-top:4px solid}}
.card-me{{background:#F0F6FF;border-color:#4A90D9}}
.card-her{{background:#FFF0F5;border-color:#FF6B9D}}
.card h3{{font-size:1.05em;margin-bottom:12px}}
.card-me h3{{color:#4A90D9}}
.card-her h3{{color:#FF6B9D}}
.row{{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid rgba(0,0,0,.05);font-size:.88em}}
.row b{{color:#333}}

/* 标签 */
.tag{{display:inline-block;border-radius:20px;padding:3px 11px;font-size:.82em;margin:3px}}
.tag-blue{{background:#E8F1FB;color:#4A90D9}}
.tag-pink{{background:#FFE8F2;color:#C84B8C}}

/* 高亮框 */
.hbox{{background:linear-gradient(135deg,#FFF5F7,#FFF0FA);border-radius:14px;padding:22px;margin:16px 0;border-left:4px solid #FF6B9D}}
.hbox h4{{color:#C84B8C;margin-bottom:10px;font-size:1em}}
.hbox .row2{{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #FFD6E7;font-size:.88em}}

/* 聊天气泡 */
.chat-wrap{{background:#f3f3f5;border-radius:12px;padding:18px;margin:16px 0;max-height:340px;overflow-y:auto}}
.crow{{display:flex;align-items:flex-start;margin:7px 0;gap:7px}}
.crow.me{{flex-direction:row-reverse}}
.clbl{{font-size:.72em;color:#aaa;white-space:nowrap;padding-top:5px;min-width:24px;text-align:center}}
.bbl{{border-radius:18px;padding:8px 14px;max-width:68%;font-size:.88em;line-height:1.55;word-break:break-all}}
.bbl-me{{background:linear-gradient(135deg,#4A90D9,#357ABD);color:#fff;border-radius:18px 4px 18px 18px}}
.bbl-her{{background:linear-gradient(135deg,#FF6B9D,#E8558C);color:#fff;border-radius:4px 18px 18px 18px}}

/* 深度分析 */
.deep{{background:linear-gradient(135deg,#FFF8FA,#FFF5FF);border-radius:16px;padding:32px 36px;line-height:1.95;font-size:1.02em;border:1px solid #FFE4EC}}
.deep p{{margin:8px 0;color:#3a3a3a}}
.deep .section-heading{{color:#C84B8C;font-size:1.05em;font-weight:700;margin:22px 0 8px;padding-left:10px;border-left:3px solid #FF6B9D}}

footer{{text-align:center;padding:32px;color:#bbb;font-size:.82em}}
</style>
</head>
<body>

<div class="hd">
  <h1>💕 我和芝芝的聊天记录</h1>
  <p>2022年8月 — 2026年5月 · 数据分析报告</p>
  <p style="opacity:.75;font-size:.92em;margin-top:6px">共 {total:,} 条消息 · 横跨 {days_span} 天</p>
</div>

<div class="wrap">

<!-- KPI -->
<div class="kpi-grid">
  <div class="kpi"><div class="num">{total:,}</div><div class="lbl">💬 消息总数</div></div>
  <div class="kpi"><div class="num">{days_span}</div><div class="lbl">📅 相识天数</div></div>
  <div class="kpi"><div class="num">{int(total/max(days_span,1))}</div><div class="lbl">📊 日均消息</div></div>
  <div class="kpi"><div class="num">{late_count:,}</div><div class="lbl">🌙 深夜消息(0-5点)</div></div>
  <div class="kpi"><div class="num">{max_streak}</div><div class="lbl">🔥 最长连续天数</div></div>
  <div class="kpi"><div class="num">{avg_reply_me:.1f}/{avg_reply_her:.1f}</div><div class="lbl">⚡ 我/她回复时长(分)</div></div>
</div>

<!-- 1. 消息总览 -->
<div class="sec">
  <h2><span class="ico">📊</span>消息总览</h2>

  <div class="cards">
    <div class="card card-me">
      <h3>🧑 我</h3>
      <div class="row"><span>发送消息</span><b>{me_count:,} 条</b></div>
      <div class="row"><span>占比</span><b>{me_pct:.1f}%</b></div>
      <div class="row"><span>消息中位长度</span><b>{me_len.median():.0f} 字</b></div>
      <div class="row"><span>中位回复时长</span><b>{avg_reply_me:.1f} 分钟</b></div>
      <div class="row"><span>主动发起对话</span><b>{initiate_me:,} 次</b></div>
    </div>
    <div class="card card-her">
      <h3>👧 芝芝</h3>
      <div class="row"><span>发送消息</span><b>{her_count:,} 条</b></div>
      <div class="row"><span>占比</span><b>{her_pct:.1f}%</b></div>
      <div class="row"><span>消息中位长度</span><b>{her_len.median():.0f} 字</b></div>
      <div class="row"><span>中位回复时长</span><b>{avg_reply_her:.1f} 分钟</b></div>
      <div class="row"><span>主动发起对话</span><b>{initiate_her:,} 次</b></div>
    </div>
  </div>

  <div class="chart">{img('overview', '消息总览')}</div>
  <div class="chart">{img('monthly_trend', '每月趋势')}</div>
  <div class="chart">{img('hourly', '每小时分布')}</div>
  <div class="chart">{img('heatmap', '热力图')}</div>
</div>

<!-- 2. 词云 -->
<div class="sec">
  <h2><span class="ico">☁️</span>词云分析</h2>
  <p style="color:#888;margin-bottom:18px">使用 jieba 中文分词，过滤停用词后统计高频词汇</p>
  <div class="two">
    <div class="chart">{img('wc_me', '我的词云')}</div>
    <div class="chart">{img('wc_her', '芝芝词云')}</div>
  </div>
  <div class="hbox">
    <h4>我的高频词 Top20</h4>
    {''.join([f'<span class="tag tag-blue">{w}<small style="opacity:.7"> {c}</small></span>' for w, c in me_wf.most_common(20)])}
  </div>
  <div class="hbox" style="border-left-color:#9B59B6">
    <h4 style="color:#9B59B6">芝芝的高频词 Top20</h4>
    {''.join([f'<span class="tag tag-pink">{w}<small style="opacity:.7"> {c}</small></span>' for w, c in her_wf.most_common(20)])}
  </div>
</div>

<!-- 3. 情感分析 -->
<div class="sec">
  <h2><span class="ico">💭</span>情感分析</h2>
  <p style="color:#888;margin-bottom:18px">SnowNLP 对每月文字消息采样评分（绿色=积极区域 / 红色=消极区域）</p>
  <div class="chart">{img('sentiment', '情感趋势')}</div>
  <div class="two">
    <div class="hbox"><h4>🌟 情感最积极的月份</h4><p style="font-size:1.1em;font-weight:700;color:#C84B8C">{best_month}</p><p style="font-size:.9em;color:#666">情感均值 {monthly_sent.get(best_month,{}).get('avg',0):.3f}</p></div>
    <div class="hbox" style="border-left-color:#9E9E9E"><h4 style="color:#666">😔 情感最低落的月份</h4><p style="font-size:1.1em;font-weight:700;color:#888">{worst_month}</p><p style="font-size:.9em;color:#666">情感均值 {monthly_sent.get(worst_month,{}).get('avg',0):.3f}</p></div>
  </div>
  <div class="chart">{img('emotion_words', '情感词')}</div>
</div>

<!-- 4. 常规分析 -->
<div class="sec">
  <h2><span class="ico">📈</span>常规分析</h2>

  <div class="chart">{img('top10', 'Top10天')}</div>

  <div class="hbox" style="margin:20px 0">
    <h4>🔥 发消息最多的日子 Top10</h4>
    {''.join([f'<div class="hbox row2"><span>#{i+1} &nbsp; {str(d)}</span><b>{c} 条</b></div>' for i, (d, c) in enumerate(top10.items())])}
  </div>

  <div class="chart">{img('len_emoji', '长度与表情')}</div>

  <div class="two">
    <div class="hbox">
      <h4>🌙 深夜聊天统计（0-5点）</h4>
      <p>深夜消息：<b>{late_count:,}</b> 条，占 <b>{late_rate:.1f}%</b></p>
      <p style="margin-top:8px;font-size:.88em;color:#888">深夜最活跃 Top3：</p>
      {''.join([f'<div style="font-size:.85em;padding:3px 0;color:#555">{str(d)} · {c} 条</div>' for d,c in late_days.items()])}
    </div>
    <div class="hbox">
      <h4>🔗 连续聊天记录</h4>
      <p>最长连续聊天 <b>{max_streak}</b> 天</p>
      <p style="font-size:.88em;color:#666;margin-top:4px">{best_start} — {best_end}</p>
      <p style="margin-top:12px;font-size:.88em;color:#888">最常用表情 Top5：</p>
      {''.join([f'<span class="tag tag-pink">[{e[0]}] {e[1]}</span>' for e in emoji_cnt.most_common(5)])}
    </div>
  </div>

  <div class="two">
    <div class="chart">{img('radar', '雷达图')}</div>
    <div class="chart">{img('topic_radar', '话题雷达')}</div>
  </div>
</div>

<!-- 5. 深度解读 -->
<div class="sec">
  <h2><span class="ico">💌</span>深度情感解读</h2>
  <p style="color:#888;margin-bottom:22px">基于全量聊天记录数据，作为旁观者写的一份观察报告</p>

  <div class="hbox" style="margin-bottom:24px">
    <h4>📖 你们相识的第一天（2022年8月19日）</h4>
    {chat_bubbles(early_msgs)}
  </div>

  <div class="deep">
    {_analysis_html}
  </div>

  <div class="hbox" style="margin-top:24px">
    <h4>💕 消息最密集时期（{peak_month_str}）样本</h4>
    {chat_bubbles(peak_msgs)}
  </div>

  <div class="hbox" style="margin-top:16px">
    <h4>📅 最近的聊天（2026年起）</h4>
    {chat_bubbles(recent_msgs)}
  </div>
</div>

</div>

<footer>
  <p>📊 分析基于 {total:,} 条消息 · 生成于 {datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
  <p style="margin-top:6px">数据仅供私人查看</p>
</footer>

</body>
</html>"""

with open(OUTPUT, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"\n✅ 报告已生成：{OUTPUT}")
print(f"   文件大小：{os.path.getsize(OUTPUT)/1024/1024:.1f} MB")
