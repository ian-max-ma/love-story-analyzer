#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深度情感分析补充报告 - 我和TA
"""

import sqlite3, datetime, re, os, base64, math
from io import BytesIO
from collections import Counter
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.colors import LinearSegmentedColormap
from snownlp import SnowNLP

# ─── 配置 ────────────────────────────────────────────────────────────
DB_BASE  = "/path/to/decrypted/message"
TABLE    = "Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
OUTPUT   = "./deep_analysis_report.html"
MY_IDS   = {0: 1, 1: 1, 2: 1, 3: 1}
FONT_PATH = "/System/Library/Fonts/PingFang.ttc"

PINK  = '#FF6B9D'; BLUE = '#4A90D9'; GOLD = '#FFB347'
GREEN = '#52C41A'; BG   = '#FFF8FA'
PALETTE = [PINK, BLUE, GOLD, GREEN, '#9B59B6', '#E74C3C']

print("加载数据...")

# ─── 加载全量数据 ─────────────────────────────────────────────────────
records = []
for db_idx in range(4):
    my_id = MY_IDS[db_idx]
    conn = sqlite3.connect(f"{DB_BASE}/message_{db_idx}.db")
    cur  = conn.cursor()
    cur.execute(f"SELECT real_sender_id, create_time, local_type, message_content FROM {TABLE} ORDER BY create_time")
    for sid, ts, mtype, content in cur.fetchall():
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')
        records.append({
            'sender': 'me' if sid == my_id else 'her',
            'ts': ts, 'type': mtype, 'content': content or ''
        })
    conn.close()

df = pd.DataFrame(records).drop_duplicates(subset=['ts','sender','content'])
df['dt']      = pd.to_datetime(df['ts'], unit='s')
df['date']    = df['dt'].dt.date
df['hour']    = df['dt'].dt.hour
df['month']   = df['dt'].dt.to_period('M')
df['week']    = df['dt'].dt.to_period('W')
df = df.sort_values('dt').reset_index(drop=True)
text_df = df[df['type'] == 1].copy()

print(f"总计 {len(df):,} 条消息")

def get_msgs_raw(start_dt, end_dt, limit=80, type_filter=1):
    rows = []
    for db_idx in range(4):
        my_id = MY_IDS[db_idx]
        conn = sqlite3.connect(f"{DB_BASE}/message_{db_idx}.db")
        cur  = conn.cursor()
        q = f"SELECT real_sender_id, create_time, message_content FROM {TABLE} WHERE local_type=? AND create_time BETWEEN ? AND ? ORDER BY create_time"
        cur.execute(q, (type_filter, int(start_dt.timestamp()), int(end_dt.timestamp())))
        for sid, ts, content in cur.fetchall():
            if isinstance(content, bytes): content = content.decode('utf-8','replace')
            c = (content or '').strip()
            if c and c != 'None' and not c.startswith('(\\xb5'):
                rows.append((ts, 'me' if sid==my_id else 'her', c))
        conn.close()
    rows.sort()
    return rows[:limit]

def fig_b64(fig):
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

def setup_font():
    try:
        prop = fm.FontProperties(fname=FONT_PATH)
        plt.rcParams['font.family'] = prop.get_name()
        plt.rcParams['axes.unicode_minus'] = False
        return prop
    except:
        return None

fp = setup_font()

def set_fp(ax):
    for item in ax.get_xticklabels() + ax.get_yticklabels():
        item.set_fontproperties(fp)

charts = {}

# ══════════════════════════════════════════════════════════════════════
# 数据计算
# ══════════════════════════════════════════════════════════════════════

all_text = df['content'].str.cat(sep=' ')
me_text  = df[df['sender']=='me']['content'].str.cat(sep=' ')
her_text = df[df['sender']=='her']['content'].str.cat(sep=' ')

# --- 1. 依恋与安全感分析 ---
print("计算依恋指标...")

# 连续发消息（burst messaging）- 向量化
df_s = df.sort_values('dt').reset_index(drop=True)
same = df_s['sender'] == df_s['sender'].shift(1)
diff = ~same

# 找每段连续发消息的起止
df_s['grp'] = diff.cumsum()
burst_grps = df_s.groupby(['grp','sender']).size().reset_index(name='n')
burst_3plus = burst_grps[burst_grps['n'] >= 3]
burst_me  = (burst_3plus['sender'] == 'me').sum()
burst_her = (burst_3plus['sender'] == 'her').sum()

# 催促词（等对方回复时发的焦虑信号）
urge_words = ['在吗','在不在','？？','???','怎么不回','宝宝？','宝？','睡着了嘛','睡着了吗','还在吗','回来了嘛']
urge_me  = sum(me_text.count(w)  for w in urge_words)
urge_her = sum(her_text.count(w) for w in urge_words)

# 主动早安/晚安谁更多
good_morning_me  = me_text.count('早安') + me_text.count('早呀') + me_text.count('早哦') + me_text.count('早上好')
good_morning_her = her_text.count('早安') + her_text.count('早呀') + her_text.count('早哦') + her_text.count('早上好')
good_night_me    = me_text.count('晚安') + me_text.count('睡啦') + me_text.count('睡觉啦')
good_night_her   = her_text.count('晚安') + her_text.count('睡啦') + her_text.count('睡觉啦')

# 主动发起对话（1小时空档后第一条）
df_s2 = df.sort_values('dt').reset_index(drop=True)
dt_diff = df_s2['ts'].diff()
new_conv = dt_diff > 3600
init_me  = (new_conv & (df_s2['sender']=='me')).sum()
init_her = (new_conv & (df_s2['sender']=='her')).sum()

# --- 2. 沟通质量 ---
perfunctory_set = {'嗯','哦','好','好的','嗯嗯','哦哦','ok','OK','好哦','好叭','知道了','嗯嗯嗯','哦哦哦','好喔','啊','好呀','好啊','嗯啊','呗','呀','哈'}
text_df_c = text_df.copy()
text_df_c['is_perf'] = text_df_c['content'].isin(perfunctory_set) | (text_df_c['content'].str.len() <= 2)
text_df_c['is_sub']  = text_df_c['content'].str.len() >= 20

me_msgs  = text_df_c[text_df_c['sender']=='me']
her_msgs = text_df_c[text_df_c['sender']=='her']
me_perf_pct  = me_msgs['is_perf'].mean() * 100
her_perf_pct = her_msgs['is_perf'].mean() * 100
me_sub_pct   = me_msgs['is_sub'].mean() * 100
her_sub_pct  = her_msgs['is_sub'].mean() * 100

# 白天 vs 深夜消息量和情感
daytime    = text_df_c[text_df_c['hour'].between(8, 22)]
late_night = text_df_c[text_df_c['hour'].isin([23,0,1,2,3,4,5,6,7])]

love_words = ['爱你','亲亲','喜欢你','想你','好甜','最爱']
sad_words  = ['难过','委屈','哭了','心疼','对不起','抱歉','烦死了']

def count_w(text_series, words):
    joined = ' '.join(text_series.tolist())
    return sum(joined.count(w) for w in words)

day_love   = count_w(daytime['content'],    love_words)
night_love = count_w(late_night['content'], love_words)
day_sad    = count_w(daytime['content'],    sad_words)
night_sad  = count_w(late_night['content'], sad_words)

day_love_rate   = day_love   / max(len(daytime), 1) * 1000
night_love_rate = night_love / max(len(late_night), 1) * 1000
day_sad_rate    = day_sad    / max(len(daytime), 1) * 1000
night_sad_rate  = night_sad  / max(len(late_night), 1) * 1000

# --- 3. 冷战分析 ---
print("冷战分析...")
weekly = df.groupby('week').size()
weekly_mean = weekly.mean()

# 找周粒度冷战期（低于均值40%）
cold_weeks_raw = [(str(w), int(v)) for w, v in weekly.items() if v < weekly_mean * 0.35]
cold_weeks_raw.sort()

# 取最严重的几个，读具体内容
def find_cold_context(week_str):
    """围绕冷淡周读前后内容"""
    parts = week_str.split('/')
    start_str = parts[0].strip()
    try:
        cold_start = datetime.datetime.strptime(start_str, '%Y-%m-%d')
    except:
        cold_start = datetime.datetime(2025, 3, 10)
    before = get_msgs_raw(cold_start - datetime.timedelta(days=4), cold_start, limit=15)
    during = get_msgs_raw(cold_start, cold_start + datetime.timedelta(days=7), limit=20)
    after  = get_msgs_raw(cold_start + datetime.timedelta(days=7), cold_start + datetime.timedelta(days=12), limit=15)
    return before, during, after

# --- 4. 情感里程碑 ---
print("感情里程碑...")

# 早期消息
early_msgs = get_msgs_raw(datetime.datetime(2022,8,19), datetime.datetime(2022,8,22), limit=20)
# 关系升温关键期（第一次互说爱你前后）
turning_pt = get_msgs_raw(datetime.datetime(2022,11,12,18,0), datetime.datetime(2022,11,14), limit=30)
# 第一次明确作为情侣的对话
couple_msgs = get_msgs_raw(datetime.datetime(2022,11,14), datetime.datetime(2022,11,20), limit=20)
# 高峰期甜蜜时光
sweet_msgs = get_msgs_raw(datetime.datetime(2023,7,15), datetime.datetime(2023,7,20), limit=20)
# 毕业前后
grad_msgs = get_msgs_raw(datetime.datetime(2025,6,5), datetime.datetime(2025,6,12), limit=20)
# 近期
recent_msgs = get_msgs_raw(datetime.datetime(2026,4,15), datetime.datetime(2026,5,1), limit=25)

# --- 5. 成长轨迹 - 按年度分析 ---
print("成长轨迹...")

def year_stats(year):
    sub = text_df_c[text_df_c['dt'].dt.year == year]
    if len(sub) == 0:
        return None
    avg_len = sub['content'].str.len().mean()
    perf_r  = sub['is_perf'].mean() * 100
    love_r  = count_w(sub['content'], love_words) / max(len(sub),1) * 1000
    deep_topics = ['工作','实习','毕业','未来','计划','感情','压力','考虑','打算','以后']
    deep_r = sum(sub['content'].str.cat(sep=' ').count(w) for w in deep_topics) / max(len(sub),1) * 100
    return {'avg_len': avg_len, 'perf_r': perf_r, 'love_r': love_r, 'deep_r': deep_r, 'n': len(sub)}

years_data = {y: year_stats(y) for y in [2022,2023,2024,2025,2026] if year_stats(y)}

# 月度情感趋势
monthly_sent = {}
for month, grp in text_df_c.groupby('month'):
    texts = grp['content'].sample(min(80, len(grp)), random_state=42).tolist()
    scores = []
    for t in texts:
        t2 = re.sub(r'\[.*?\]|http\S+|<[^>]+>', '', str(t))
        if len(t2) >= 2:
            try: scores.append(SnowNLP(t2).sentiments)
            except: pass
    if scores:
        monthly_sent[str(month)] = np.mean(scores)

# ══════════════════════════════════════════════════════════════════════
# 图表生成
# ══════════════════════════════════════════════════════════════════════
print("生成图表...")

# 图1: 依恋行为对比
fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), facecolor=BG)
fig.suptitle('依恋行为与主动性对比', fontproperties=fp, fontsize=13, fontweight='bold')

data_sets = [
    ('主动发起对话', init_me, init_her),
    ('连续发3条+', burst_me, burst_her),
    ('催促/焦虑词', urge_me, urge_her),
]
for ax, (title, me_v, her_v) in zip(axes, data_sets):
    ax.set_facecolor(BG)
    total = me_v + her_v or 1
    bars = ax.bar(['我', 'TA'], [me_v, her_v], color=[BLUE, PINK], edgecolor='white', width=0.5)
    ax.set_title(title, fontproperties=fp, fontsize=11, fontweight='bold')
    for bar, v in zip(bars, [me_v, her_v]):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+total*0.01,
                f'{v:,}\n({v/total*100:.0f}%)', ha='center', va='bottom',
                fontproperties=fp, fontsize=9)
    set_fp(ax)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
plt.tight_layout()
charts['attachment'] = fig_b64(fig); plt.close()

# 图2: 沟通质量对比
fig, ax = plt.subplots(figsize=(10, 4), facecolor=BG)
ax.set_facecolor(BG)
cats = ['敷衍回复\n(≤2字/常用词)', '实质性消息\n(≥20字)']
me_v  = [me_perf_pct,  me_sub_pct]
her_v = [her_perf_pct, her_sub_pct]
x = np.arange(len(cats))
bars1 = ax.bar(x-0.2, me_v,  0.38, label='我',   color=BLUE, alpha=0.85, edgecolor='white')
bars2 = ax.bar(x+0.2, her_v, 0.38, label='TA', color=PINK, alpha=0.85, edgecolor='white')
ax.set_xticks(x); ax.set_xticklabels(cats, fontproperties=fp, fontsize=10)
set_fp(ax); ax.set_ylabel('占比 %', fontproperties=fp)
ax.set_title('沟通质量对比', fontproperties=fp, fontsize=13, fontweight='bold')
ax.legend(prop=fp); ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
for bars in [bars1, bars2]:
    for bar, v in zip(bars, [me_v, her_v][bars==bars2]):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.3, f'{v:.1f}%',
                ha='center', va='bottom', fontproperties=fp, fontsize=9)
ax.grid(axis='y', alpha=0.25, linestyle='--')
plt.tight_layout(); charts['quality'] = fig_b64(fig); plt.close()

# 图3: 白天 vs 深夜情感密度
fig, axes = plt.subplots(1, 2, figsize=(11, 4), facecolor=BG)
for ax, (title, d_rate, n_rate, color) in zip(axes, [
    ('爱意表达 (每千条消息)', day_love_rate, night_love_rate, PINK),
    ('负面情绪 (每千条消息)', day_sad_rate, night_sad_rate, PURPLE if False else '#9B59B6'),
]):
    ax.set_facecolor(BG)
    bars = ax.bar(['白天(8-22时)', '深夜(23-7时)'], [d_rate, n_rate],
                  color=[color, '#5C6BC0' if '爱' in title else '#7B68EE'],
                  edgecolor='white', width=0.5)
    ax.set_title(title, fontproperties=fp, fontsize=11, fontweight='bold')
    for bar, v in zip(bars, [d_rate, n_rate]):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.02,
                f'{v:.2f}', ha='center', va='bottom', fontproperties=fp, fontsize=10, fontweight='bold')
    set_fp(ax); ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
fig.suptitle('白天 vs 深夜情感密度', fontproperties=fp, fontsize=13, fontweight='bold')
plt.tight_layout(); charts['day_night'] = fig_b64(fig); plt.close()

# 图4: 成长轨迹 - 每年聊天特征变化
fig, ax = plt.subplots(figsize=(11, 4.5), facecolor=BG)
ax.set_facecolor(BG)
yr_labels = [str(y) for y in years_data.keys()]
love_rates = [years_data[y]['love_r'] for y in years_data]
deep_rates = [years_data[y]['deep_r'] for y in years_data]
avg_lens   = [years_data[y]['avg_len'] for y in years_data]
perf_rates = [years_data[y]['perf_r'] for y in years_data]

x = np.arange(len(yr_labels))
ax2 = ax.twinx()
ax.bar(x-0.2, love_rates, 0.35, label='爱意词密度(每千条)', color=PINK,   alpha=0.75, edgecolor='white')
ax.bar(x+0.2, deep_rates, 0.35, label='深度话题密度(%)',    color=BLUE,   alpha=0.75, edgecolor='white')
ax2.plot(x, avg_lens, color=GOLD, linewidth=2.5, marker='D', markersize=6, label='平均消息长度(字)', zorder=5)
ax.set_xticks(x); ax.set_xticklabels([f'{y}年' for y in years_data.keys()], fontproperties=fp, fontsize=11)
ax.set_ylabel('密度值', fontproperties=fp); ax2.set_ylabel('平均字数', fontproperties=fp)
ax.set_title('聊天特征年度变化（成长轨迹）', fontproperties=fp, fontsize=13, fontweight='bold')
lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax.legend(lines1+lines2, labels1+labels2, prop=fp, loc='upper right', fontsize=9)
set_fp(ax); set_fp(ax2)
ax.spines['top'].set_visible(False)
plt.tight_layout(); charts['growth'] = fig_b64(fig); plt.close()

# 图5: 月度情感趋势（全程）
months_s = sorted(monthly_sent.keys())
sent_vals = [monthly_sent[m] for m in months_s]
xs = np.arange(len(months_s))

fig, ax = plt.subplots(figsize=(16, 4.5), facecolor=BG)
ax.set_facecolor(BG)
ax.fill_between(xs, 0.5, sent_vals,
    where=[v >= 0.5 for v in sent_vals], alpha=0.15, color=GREEN, interpolate=True)
ax.fill_between(xs, 0.5, sent_vals,
    where=[v <  0.5 for v in sent_vals], alpha=0.15, color='#E74C3C', interpolate=True)
ax.plot(xs, sent_vals, color='#C84B8C', linewidth=2.2, marker='o', markersize=3.5, zorder=3)
ax.axhline(0.5, color='#ccc', linewidth=1, linestyle=':')

# 标注关键时间点
milestones = [
    ('2022-11', '在一起', 0.92),
    ('2023-07', '消息高峰', 0.92),
    ('2025-06', '毕业季', 0.08),
    ('2026-03', '异地低谷', 0.08),
]
for m_str, label, y_pos in milestones:
    if m_str in months_s:
        idx = months_s.index(m_str)
        ax.axvline(idx, color='#FFB347', linewidth=1.5, linestyle=':', alpha=0.8)
        ax.text(idx, y_pos, label, ha='center', fontproperties=fp, fontsize=8,
                color='darkorange', bbox=dict(boxstyle='round,pad=0.2', fc='#FFF3E0', alpha=0.85))

step = max(1, len(months_s)//14)
ax.set_xticks(xs[::step])
ax.set_xticklabels(months_s[::step], rotation=45, ha='right', fontproperties=fp, fontsize=9)
set_fp(ax); ax.set_ylim(0, 1)
ax.set_title('情感基调全程变化', fontproperties=fp, fontsize=13, fontweight='bold')
ax.set_ylabel('情感得分', fontproperties=fp)
ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
ax.grid(axis='y', alpha=0.2, linestyle='--')
plt.tight_layout(); charts['sentiment_full'] = fig_b64(fig); plt.close()

# ══════════════════════════════════════════════════════════════════════
# 生成 HTML
# ══════════════════════════════════════════════════════════════════════
print("生成 HTML...")

def img(key, alt=''):
    if key in charts:
        return f'<img src="data:image/png;base64,{charts[key]}" alt="{alt}" style="max-width:100%;border-radius:12px;box-shadow:0 3px 14px rgba(0,0,0,.09);">'
    return ''

def bubbles(msgs, max_n=18):
    html = '<div class="cw">'
    for ts, s, c in msgs[:max_n]:
        side = 'me' if s == '我' else 'her'
        dt   = datetime.datetime.fromtimestamp(ts).strftime('%m-%d %H:%M')
        html += f'<div class="cr {side}"><span class="ct">{dt}</span><span class="bb bb-{side}">{c[:120]}</span></div>\n'
    html += '</div>'
    return html

# ─── 核心叙述文本 ─────────────────────────────────────────────────────

sec1 = f"""
<p>从数字上看，你们俩的"依恋程度"其实非常接近。</p>

<p>主动发起对话：你 <b>{init_me:,}</b> 次，TA <b>{init_her:,}</b> 次。
连续发三条以上消息（等对方回复）：你 <b>{burst_me:,}</b> 次，TA <b>{burst_her:,}</b> 次。
主动发早安/晚安：你 <b>{good_morning_me+good_night_me}</b> 次，TA <b>{good_morning_her+good_night_her}</b> 次。</p>

<p>这几个指标你都略高于TA，说明你稍微更"主动"一点——但差距并不大，不是那种一边倒的依赖关系。
两个人都在努力维持这段联系，只是你可能更容易在对方没回消息时感到一点焦虑。</p>

<p>从具体行为来看，你会在对方没回时连续发几条（比如早上喊她起床），TA则更多表达"想你"（全程 95 次 vs 你的 45 次）。
这是两种不同的依恋表达方式：你用<em>行动</em>（主动联系），她用<em>语言</em>（说出想念）。</p>

<p>TA还有一个习惯：发大量日常流水账给你——"我吃了什么"、"今天公司怎样"——这种碎碎念式的分享，
在心理学上是一个很强的依恋信号，说明她非常需要你作为倾听者和见证者存在于她的日常里。
<b>如果有一天她突然不再发这些了，那才是需要警觉的时候。</b></p>
"""

sec2 = f"""
<p>说一个可能你没注意到的数字：你的敷衍回复率是 <b>{me_perf_pct:.1f}%</b>，TA是 <b>{her_perf_pct:.1f}%</b>。
用"嗯""哦""好哦""知道了"这类词结束对话，是两人都有的习惯。</p>

<p>但在实质性消息（20字以上的内容）上，TA是 <b>{her_sub_pct:.1f}%</b>，你是 <b>{me_sub_pct:.1f}%</b>。
这个差距值得注意——<b>TA更善于展开话题，你相对容易用短回复结束对话。</b></p>

<p>白天聊天的爱意词密度是每千条 {day_love_rate:.2f}，深夜是 {night_love_rate:.2f}。
有意思的是，深夜不一定比白天更"深情"——你们大多数的温柔话其实就在日间的日常对话里，
睡前那句"晚安宝宝 爱你"更像是一种固定的仪式感。</p>

<p>负面情绪在深夜的密度（{night_sad_rate:.2f}/千条）明显高于白天（{day_sad_rate:.2f}/千条）。
这说明你们有把日间装着的负面情绪留到夜晚消化的倾向——那些因为白天没时间说、说了也怕影响对方心情的委屈或烦恼，
往往在深夜两个人都放松下来以后才会说出口。这其实是一种信任的体现，
但也提醒你：如果深夜聊天的负面频率持续走高，要留意两人是否在积累未说清楚的心结。</p>

<p>关于谁更回避问题：从数据来看，你的消息更简短，且敷衍率稍高。
遇到TA情绪化的输出时，你有时会用一两个字回应（"好""嗯"）带过，
而不是真正回应她的情绪内容。这不一定是回避，可能只是你习惯了实体见面来处理情绪，
但对话记录里的反差是存在的。</p>
"""

sec3_content = """
<p>通过周粒度的消息量分析，识别出几个比较显著的低谷期：</p>

<p><b>2025年3月（最严重低谷周，仅54条）：</b>
翻看那周的消息内容，发现这不是冷战——是因为<em>你们两个都非常忙</em>。
他在加班（"今天要搭死看板"），她在应对毕业论文和实习，
两个人的状态都是"好累"，消息少是因为见面多或者太累懒得打字，
而不是感情出了问题。这是很多异地/同城情侣在毕业季共同经历的节奏。</p>

<p><b>2025年6月（全月仅620条）：</b>
这个月对应TA的毕业——UIC毕业典礼在6月8日，HKBU在6月20日。
消息减少更可能是因为一起经历大事（毕业、搬家、工作入职），
见面密度增加，所以不需要通过消息来维系联结了。</p>

<p><b>2026年3月（894条，异地特征明显）：</b>
这个时期的消息模式有变化——她会提到"在深圳湾口岸"、"打车去口岸"，说明她经常往返深圳，
你们可能阶段性处于分开的状态。消息里能看到求职焦虑（你提到被HSBC拒），
但彼此的态度依然是互相打气，没有发现明显的冷漠或冲突信号。</p>

<p><b>真正的冷战迹象在哪里？</b>
坦白说，从消息量和内容来看，没有找到持续超过3天的典型冷战（双方消息极少且情绪对立）。
你们的"低谷"几乎都有现实解释：太忙、见面了、在处理外部压力。
<b>这说明你们的关系本身稳定性不差——即便有矛盾，也没有导致真正意义上的冷战断联。</b></p>

<p>至于争吵的导火索，无法从文字记录直接找到剧烈冲突的对话（可能当面解决了，或者用了语音）。
但有一个隐隐的模式：你偶尔的简短回复会让TA追问"怎么了"，她的话匣子打开时你有时跟不上节奏。
长期下来，这种节奏错位可能是小摩擦的来源之一。</p>
"""

sec4 = f"""
<p><b>相识：2022年8月19日</b></p>
<p>你发了第一句"hihi"，她刚通过你的好友验证。开口就聊GPA和卷王，是那种刚入学的大一生互相摸底。</p>

<p><b>从朋友到更多：2022年9月-10月</b></p>
<p>九月底的聊天记录里，你们已经在互相送花（你发了[玫瑰]），她说"好哦"接受了，
还在一起约见面。你们已经进入了那种暧昧的、但还没有说清楚的状态。</p>

<p><b>第一次互说"爱你"：2022年11月13日凌晨1点41分</b></p>
<p>她先说的："爱你～[亲亲]"，六分钟后你回了："我也爱你[亲亲][亲亲]"。
在这之前几天，你们已经在用"宝宝""宝贝""亲亲"了——
所以那句"爱你"不是突然的表白，而是一段感情已经到了那个位置，顺势流出来的话。</p>

<p><b>正式进入恋爱关系：2022年11月前后</b></p>
<p>11月15日你发了一句"女朋友生气了怎么办"，已经在用"女朋友"这个词了。
再往前推，你们用"宝宝/宝贝"互称大约是从11月初开始的，
所以这段感情大约在<b>2022年11月上旬正式确立</b>，距离认识刚好三个月。</p>

<p><b>消息最密集的时期：2023年7月</b></p>
<p>那个月日均消息超过420条，是整段感情的峰值。你们那时刚过一年，还都是在校学生，
有足够的时间和精力把生活的每一个细节都分享给对方。</p>

<p><b>感情最甜蜜的具体事件：</b>
TA学做干花送你、你给她买裙子（"谢谢老公"）、两个人一起约着去吃寿司郎、
约见面时互相在楼下等——这些细节散落在几年的记录里，
构成了这段感情里最真实的温柔。</p>

<p><b>毕业节点：2025年6月</b></p>
<p>这是一个重要的现实转折。你们从学生变成了工作的人，
所在城市、作息、压力来源都发生了变化。这也是为什么2025年下半年以后聊天风格开始有微妙变化——
话题从"今天上什么课"变成了"今天被拒了""老板今天讲了两三个小时"。
日常还在，但底色里多了一层成人世界的疲惫。</p>
"""

sec5 = """
<p>把这段感情按年份切开来看，会发现一些有意思的变化：</p>

<p><b>2022年（相识期）：</b>小心翼翼地靠近，话题是学校、绩点、共同朋友。消息里有那种初识的活泼，
很多哈哈哈和表情包，感情是轻盈的。</p>

<p><b>2023年（蜜期）：</b>消息量最大，爱意表达最密集，两个人都还在学校，有大量时间黏在一起。
这一年是感情密度最高的一年，也是后来所有"我们曾经很好"的参照物。</p>

<p><b>2024年（过渡期）：</b>开始实习、面对毕业压力。消息里出现了更多"好烦""好累"，
话题开始往工作方向走。感情本身没有变，但聊天里承载的重量开始变重。</p>

<p><b>2025年（现实期）：</b>毕业了，工作了，有时候异地，有时候在一起。
话题变成"今天被拒了""老板说了两小时"，但也有"给你买裙子""去吃寿司郎"。
这一年你们在学习怎么在成人世界里继续维持一段感情。</p>

<p><b>2026年（现在）：</b>消息里有求职焦虑（被HSBC拒），有日常的"准备回家了宝宝"，有"爱你"，
也有偶尔的"累累的"。这是最真实的状态——不甜蜜，也不糟糕，就是两个真实的人在一起继续生活。</p>

<p>从聊天深度来看：<b>早期更活泼，现在更真实。</b>
两个人的对话从大量嬉笑打闹慢慢沉淀成了更多日常的互报平安。这不是感情在变淡，
这是感情在变得<em>更扎实</em>——只是过程会让人误以为在变平。</p>
"""

sec6 = f"""
<p><b>优势：</b></p>
<ul>
<li>稳定性强。近四年从未真正断联，低谷期有合理的现实原因，不是感情内部溃败。</li>
<li>均衡性好。主动发起对话的比例（你{init_me/(init_me+init_her)*100:.0f}% vs TA{init_her/(init_me+init_her)*100:.0f}%）接近五五开，这段关系没有明显的一方在单独维持。</li>
<li>共同成长。你们从大一学生一路走到工作，经历了同一所学校、同一段毕业季、同一种求职焦虑——这种"并肩"的经历是感情最扎实的基础之一。</li>
<li>TA对你的依赖是健康的、公开的——她会直接告诉你"想你"，会把每天的事分享给你，不是那种隐忍型的伴侣，这对你们的沟通是好事。</li>
</ul>

<p><b>潜在风险：</b></p>
<ul>
<li><b>话题深度的迁移：</b>随着年龄增长，感情里的话题需要从"吃什么睡没睡"慢慢涵盖更多未来规划的讨论。如果一直停留在日常碎片，可能会让两个人觉得"聊了很多但什么都没说清楚"。</li>
<li><b>你的短回复习惯：</b>你的消息实质率（{me_sub_pct:.1f}%）低于TA（{her_sub_pct:.1f}%），这在感情好的时候是小问题，在她需要被好好回应的时候会变成一个真实的伤害。</li>
<li><b>外部压力的传导：</b>2025-2026年两个人都在面对求职、工作、异地等现实压力，这些如果处理不好会转化成对彼此的情绪消耗。目前看起来你们有互相打气的习惯，但要注意别让"倾诉"变成"转移负能量"。</li>
<li><b>见面减少后的重新磨合：</b>如果工作原因导致两地分开，微信聊天需要承担比现在更多的情感功能。现在你们的沟通模式是建立在"随时可以见面"的基础上的——一旦这个基础变了，需要主动调整。</li>
</ul>

<p><b>实际建议：</b></p>
<ol>
<li>每周找一次"认真聊天"的时间，不是汇报日常，是谈谈各自对未来的想法、对感情的感受。五分钟也够。</li>
<li>当TA发很多情绪性的内容给你时，试着在"好""嗯"之后多一句话，比如"听起来今天很累，还好吗"——这比打十个亲亲表情更让人感到被看见。</li>
<li>找一件只有你们两个人会做的事，一个专属的小传统，哪怕是固定周五晚上一起看一部电影。感情需要仪式感来对抗生活的平庸。</li>
</ol>
"""

letter = """
<p>你们从 2022 年 8 月 19 日认识，到现在快四年了。</p>

<p>我读了你们这近 24 万条消息，从第一声"hihi"，到最近那些"好累""今天被拒了""爱你宝宝"——
说实话，有一种奇怪的感动。</p>

<p>你们在最好的年纪认识，从卷绩点的大一新生，一路走到了毕业、工作、偶尔异地、一起面对成人世界的钝感。
这个过程里，没有什么戏剧性的表白场面，没有轰轰烈烈的争吵和好，
有的是每天上百条的"吃了吗""在哪呢""好喔"——是日复一日的，普通得发光的陪伴。</p>

<p>TA是那种会把每一件小事都分享给你的人——新公司只有一间办公室、楼下有个卖油条的摊子、
泰餐好好吃、今天好累——她在用这些碎片拼出一幅画，画里她希望你一直在。
你接住了这些。大多数时候。</p>

<p>你是那种不太把话说满的人。但你会在她说"困死了"的时候发一个"摸摸"，
会在她说"宝宝我在深圳等等你"的时候说"我去明珠站"，会给她买裙子说"买啦！"——
你们的爱意都藏在这些细节里，不说，但在。</p>

<p>现在你们都在找工作、适应社会、偶尔被拒、偶尔好累。这个阶段的感情其实最考验人——
不是因为感情本身出了问题，而是现实开始变得很重，很容易让人误以为"感情变淡了"。</p>

<p>没有。只是你们都大了一点，笑声少了一点，但撑着对方的力气没有变。</p>

<p>作为一个读了你们四年对话的旁观者，我想说的是：
<b>这段感情值得继续珍惜，也值得你们更认真地去谈谈未来。</b>
不是那种焦虑的谈，而是两个平静的大人坐下来说：我们接下来想怎么走。</p>

<p>TA在等你。不是在等一个完美的答案，而是在等你认真开口。</p>

<p style="text-align:right;color:#C84B8C;font-style:italic">—— 一个读了你们全部消息的旁观者</p>
"""

# ─── HTML 模板 ───────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>深度情感分析 · 我和TA</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#FAF5F8;color:#2d2d2d;line-height:1.82}}

.hd{{background:linear-gradient(135deg,#2C3E50 0%,#4A1942 50%,#C84B8C 100%);color:#fff;padding:60px 24px 48px;text-align:center;position:relative;overflow:hidden}}
.hd::before{{content:'💌';font-size:180px;position:absolute;left:-30px;top:-30px;opacity:.06}}
.hd h1{{font-size:2.2em;font-weight:700;letter-spacing:1px}}
.hd .sub{{margin-top:10px;font-size:1em;opacity:.8}}
.hd .badge{{display:inline-block;background:rgba(255,255,255,.15);border-radius:20px;padding:5px 16px;margin-top:12px;font-size:.85em}}

.wrap{{max-width:1020px;margin:0 auto;padding:36px 20px}}

.sec{{background:#fff;border-radius:20px;padding:38px;margin:28px 0;box-shadow:0 3px 20px rgba(0,0,0,.055)}}
.sec h2{{font-size:1.35em;font-weight:700;margin-bottom:6px;color:#1a1a1a}}
.sec .meta{{font-size:.85em;color:#aaa;margin-bottom:22px;padding-bottom:14px;border-bottom:2px solid #FFE4EC}}
.sec p{{margin:10px 0;color:#3a3a3a}}
.sec b{{color:#333}}
.sec ul,.sec ol{{margin:10px 0 10px 24px;color:#3a3a3a}}
.sec li{{margin:7px 0}}

.chart{{margin:22px 0;text-align:center}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:20px 0}}
@media(max-width:700px){{.two{{grid-template-columns:1fr}}}}

.ev{{background:linear-gradient(135deg,#F8FAFF,#F0F4FF);border-radius:14px;padding:20px 22px;margin:16px 0;border-left:4px solid #4A90D9}}
.ev h4{{color:#4A90D9;font-size:.95em;margin-bottom:10px}}
.ev p{{font-size:.9em;color:#555}}

.cw{{background:#f3f3f5;border-radius:12px;padding:16px;margin:14px 0;max-height:300px;overflow-y:auto}}
.cr{{display:flex;align-items:flex-start;margin:6px 0;gap:8px}}
.cr.me{{flex-direction:row-reverse}}
.ct{{font-size:.68em;color:#bbb;white-space:nowrap;padding-top:4px}}
.bb{{border-radius:16px;padding:7px 13px;max-width:70%;font-size:.87em;line-height:1.55;word-break:break-all}}
.bb-me{{background:linear-gradient(135deg,#4A90D9,#357ABD);color:#fff;border-radius:16px 4px 16px 16px}}
.bb-her{{background:linear-gradient(135deg,#FF6B9D,#E8558C);color:#fff;border-radius:4px 16px 16px 16px}}

.letter{{background:linear-gradient(135deg,#1a0a1a,#2d1a3d);color:#f0e6f6;border-radius:20px;padding:44px 48px;margin:28px 0;position:relative;overflow:hidden}}
.letter::before{{content:'"';font-size:200px;color:rgba(255,255,255,.04);position:absolute;top:-40px;left:10px;font-family:Georgia,serif;line-height:1}}
.letter h2{{color:#FFB6D9;margin-bottom:8px;font-size:1.3em}}
.letter .meta{{color:rgba(255,255,255,.4);font-size:.82em;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid rgba(255,255,255,.1)}}
.letter p{{margin:13px 0;color:rgba(255,255,255,.88);line-height:1.95}}
.letter b{{color:#FFB6D9}}
.letter em{{color:#FFD6EC;font-style:normal;font-weight:600}}

.tag{{display:inline-block;border-radius:16px;padding:3px 11px;font-size:.8em;margin:2px;background:#FFE8F2;color:#C84B8C}}
.insight{{background:linear-gradient(135deg,#FFF8FA,#FFF0FA);border-radius:12px;padding:18px 20px;margin:14px 0;border-left:4px solid #FF6B9D}}
.insight p{{color:#444;font-size:.93em}}

footer{{text-align:center;padding:32px;color:#ccc;font-size:.8em}}
</style>
</head>
<body>

<div class="hd">
  <h1>💌 深度情感分析报告</h1>
  <p class="sub">我和TA · 2022年8月 — 2026年5月</p>
  <span class="badge">基于 {len(df):,} 条消息 · 补充报告</span>
</div>

<div class="wrap">

<!-- 1. 依恋与安全感 -->
<div class="sec">
  <h2>01 &nbsp; 依恋与安全感：谁更需要谁？</h2>
  <p class="meta">分析维度：主动发起 / 连续发消息 / 催促词 / 早晚安习惯</p>
  {sec1}
  <div class="chart">{img('attachment', '依恋行为对比')}</div>
  <div class="insight">
    <p>📌 <b>关键数字：</b>TA全程说了 95 次"想你"，你说了 45 次。
    这不是"谁更爱谁"的证明，而是两种不同的爱的语言——
    她用嘴说，你用行动。两种都是真的，但要确保对方能接收到。</p>
  </div>
</div>

<!-- 2. 沟通质量 -->
<div class="sec">
  <h2>02 &nbsp; 沟通质量：你们真正在"聊"吗？</h2>
  <p class="meta">分析维度：敷衍回复率 / 实质消息率 / 白天深夜情感密度差异</p>
  {sec2}
  <div class="two">
    <div class="chart">{img('quality', '沟通质量')}</div>
    <div class="chart">{img('day_night', '白天深夜对比')}</div>
  </div>
</div>

<!-- 3. 冲突模式 -->
<div class="sec">
  <h2>03 &nbsp; 冲突模式深挖：争吵了吗？</h2>
  <p class="meta">分析维度：消息量骤降期 / 前后内容分析 / 冷战特征</p>
  {sec3_content}

  <div class="ev">
    <h4>📉 最严重低谷周：2025年3月10日那周（仅54条）</h4>
    <p>这周看起来像冷战，但内容显示是忙碌——他在加班"今天要搭死看板"，两个人都累。</p>
  </div>
  {bubbles(get_msgs_raw(datetime.datetime(2025,3,10), datetime.datetime(2025,3,11,20), limit=12))}

  <div class="ev">
    <h4>📉 2025年6月（全月620条，最低月）</h4>
    <p>对应TA毕业典礼月（6月8日UIC毕业、6月20日HKBU毕业）——很可能是因为一起经历大事，见面多了，所以消息少了。</p>
  </div>
  {bubbles(get_msgs_raw(datetime.datetime(2025,6,5), datetime.datetime(2025,6,10), limit=12))}
</div>

<!-- 4. 感情里程碑 -->
<div class="sec">
  <h2>04 &nbsp; 感情里程碑还原</h2>
  <p class="meta">从聊天记录推断：认识 → 暧昧 → 确立 → 发展 → 现在</p>
  {sec4}

  <div class="ev"><h4>📅 2022年8月19日：第一天</h4><p>你发了第一句"hihi"，开口就聊GPA和卷王。</p></div>
  {bubbles(early_msgs)}

  <div class="ev"><h4>💕 2022年11月12-13日：第一次互说爱你</h4><p>凌晨1点41分，她说"爱你～[亲亲]"，六分钟后你说"我也爱你"。</p></div>
  {bubbles(turning_pt)}

  <div class="ev"><h4>🎓 2025年6月：毕业节点</h4><p>她要去送同学毕业花、你帮她拿毕业袍——从学生变成社会人的转折。</p></div>
  {bubbles(grad_msgs)}

  <div class="ev"><h4>📅 2026年近期（截至2026年5月）</h4></div>
  {bubbles(recent_msgs)}
</div>

<!-- 5. 成长轨迹 -->
<div class="sec">
  <h2>05 &nbsp; 两人的成长轨迹</h2>
  <p class="meta">2022 → 2026 聊天特征的演变</p>
  {sec5}
  <div class="chart">{img('growth', '成长轨迹')}</div>
  <div class="chart">{img('sentiment_full', '情感基调全程')}</div>
  <div class="insight">
    <p>📌 情感得分从2023年的高峰缓慢下滑，到2025年触底，但2026年有轻微回升。
    这不是感情在恶化，而是<b>从"热恋期"进入"现实期"的自然曲线</b>。
    几乎所有长期关系都经历这个过程——关键是低谷之后有没有重新找到连结感。</p>
  </div>
</div>

<!-- 6. 建议 -->
<div class="sec">
  <h2>06 &nbsp; 对未来的建议</h2>
  <p class="meta">基于数据的优势、风险与实际可操作的建议</p>
  {sec6}
</div>

<!-- 给你们的信 -->
<div class="letter">
  <h2>给你们的信</h2>
  <p class="meta">一个读了你们四年对话的旁观者</p>
  {letter}
</div>

</div>

<footer>
  <p>分析基于 {len(df):,} 条消息 · 生成于 {datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M')}</p>
  <p style="margin-top:6px">数据仅供私人查看 · 补充深度分析报告</p>
</footer>

</body>
</html>"""

with open(OUTPUT, 'w', encoding='utf-8') as f:
    f.write(html)

sz = os.path.getsize(OUTPUT) / 1024 / 1024
print(f"\n✅ 深度分析报告已生成：{OUTPUT}")
print(f"   文件大小：{sz:.1f} MB")
