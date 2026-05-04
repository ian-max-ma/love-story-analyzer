# 微信聊天记录深度分析 · 完整项目 Prompt

> 把这份文档完整粘贴给 Claude Code，它会从头引导你完成整个流程。
> 根据实际情况修改 **【需要你填写】** 的部分。

---

## 背景说明

我想分析我和某人的微信聊天记录，生成两份 HTML 报告：
1. **基础可视化报告**（消息总览、词云、情感趋势、常规统计）
2. **深度情感分析报告**（依恋模式、沟通质量、冲突追踪、感情里程碑、给我们的信）

项目基于 [wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt) 工具解密微信数据库，然后用 Python 分析聊天记录。

---

## 第一步：解密微信数据库（如果还没做）

### macOS 操作步骤

```bash
# 1. 确保微信正在运行
# 2. 克隆项目
git clone <wechat-decrypt仓库地址>
cd wechat-decrypt
pip install -r requirements.txt

# 3. 对微信做 ad-hoc 重签名（允许读取进程内存）
sudo codesign -f -s - /Applications/WeChat.app

# 4. 提取密钥并解密（需要 sudo）
sudo python3 main.py decrypt --output ./decrypted

# 解密完成后，decrypted/ 目录下会有：
# message/message_0.db  message/message_1.db  ...
# contact/contact.db
# session/session.db
```

### Windows 操作步骤

```bash
# 管理员身份运行 PowerShell
python main.py decrypt --output ./decrypted
```

### 验证解密成功

```python
import sqlite3
conn = sqlite3.connect('./decrypted/message/message_0.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 10")
print(cur.fetchall())
conn.close()
# 应该能看到类似 Msg_xxxxxxxxxxxxxxxx 这样的表名
```

---

## 第二步：找到目标联系人的信息

### 【需要你填写】

```
我要分析的聊天对象：【填写备注名/微信名，例如：小明】
关系：【例如：女朋友、好友、同事】
大概的聊天时间跨度：【例如：2022年8月至今】
```

### 让 Claude 帮你找联系人 wxid 和消息表名

把下面这段话发给 Claude Code：

```
帮我在 ./decrypted/ 目录下找到我和【联系人名字】的聊天记录。
具体步骤：
1. 查 contact.db 里的联系人表，找到名字包含"【联系人名字】"的记录，获取 wxid
2. 根据 wxid 计算消息表名（MD5 哈希），或者直接在 message_*.db 里搜索所有 Msg_ 开头的表
3. 确认哪个表包含我们的聊天记录（检查消息数量和时间范围）
4. 找出各个 DB 文件里"我"的 real_sender_id（通常只有两个主要 sender_id，数量接近的那两个）
把结果告诉我：wxid、消息表名、各DB中我的sender_id
```

### 参考：如何确认哪个 sender_id 是"我"

```python
import sqlite3, datetime

# 检查某个 DB 里的发送者分布
conn = sqlite3.connect('./decrypted/message/message_0.db')
cur = conn.cursor()
cur.execute("SELECT real_sender_id, count(*) FROM 【消息表名】 GROUP BY real_sender_id ORDER BY count(*) DESC LIMIT 5")
print(cur.fetchall())

# 再看几条消息内容来判断哪个是你
cur.execute("SELECT real_sender_id, message_content FROM 【消息表名】 WHERE local_type=1 LIMIT 20")
for row in cur.fetchall():
    print(row[0], row[1][:50])
conn.close()
```

通常：
- 看第一条消息（加好友时的系统消息），接受好友请求的人是对方
- 看早期消息的内容判断谁是谁
- 两个主要 sender_id 数量相差不太大

---

## 第三步：填写项目配置

根据上面找到的信息，填写下面的配置：

```
# 【需要你填写，给 Claude 的配置信息】

数据库路径：./decrypted/message/
消息表名：Msg_【xxxxxxxxxxxxxxxx】（32位MD5）
数据库文件：message_0.db、message_1.db、message_2.db、message_3.db（根据实际有几个填几个）

各数据库中"我"的 real_sender_id：
  message_0.db: 【填写，例如 9】
  message_1.db: 【填写，例如 16】
  message_2.db: 【填写，例如 98】
  message_3.db: 【填写，例如 1】

聊天对象称呼：【填写，例如：小明】
关系描述：【填写，例如：女朋友，从大学同学开始认识的】
时间跨度：【例如：2022年8月 ~ 2026年5月】
总消息数（大约）：【例如：约24万条】
```

---

## 第四步：生成基础可视化报告

把下面这段完整发给 Claude Code（把【】里的内容替换掉）：

---

**帮我分析微信聊天记录，生成一份完整的可视化 HTML 报告。**

**数据配置：**
- 数据库路径：`./decrypted/message/`
- 消息表：`【消息表名】`
- 涉及数据库：`message_0.db` ~ `message_【N】.db`
- 各库中"我"的 real_sender_id 映射：`{0: 【ID0】, 1: 【ID1】, 2: 【ID2】, 3: 【ID3】}`（key=数据库编号，value=我的sender_id）
- 聊天对象：【对方称呼】
- 时间跨度：【时间跨度】

**分析内容：**

1. **消息总览**
   - 总消息数、双方发送数量和比例
   - 每月消息量趋势折线图（标注峰值）
   - 每小时活跃分布图
   - 星期×小时热力图
   - 消息类型分布（注意：local_type 大数字类型需要正确解码，例如 244813135921 = type49子类"引用回复"，解码方式：base=t%(2**32), sub=t//(2**32)）

2. **词云**
   - 用 jieba 中文分词，分别生成双方词云
   - 过滤停用词（嗯/哦/啊/的/了等）
   - 展示双方高频词 Top20

3. **情感分析**
   - 用 SnowNLP 按月分析情感变化趋势
   - 绿色区域=积极，红色区域=消极
   - 标注情感高峰和低谷月份

4. **常规分析**
   - 发消息最多的日子 Top10
   - 最常用微信表情排行（从 [表情名] 格式统计）
   - 消息长度分布对比（谁更话痨）
   - 主动发起对话比例
   - 深夜(0-5点)聊天统计
   - 最长连续聊天天数
   - 雷达图综合对比

5. **深度情感解读**（用自然语言，像朋友分析一样）
   - 感情发展脉络
   - 相处模式和称谓习惯
   - 冷淡期分析（哪些月份消息量骤降）
   - 感情最好和最低落的时期

**技术要求：**
- 先安装依赖：`pip3 install jieba wordcloud matplotlib pandas numpy snownlp emoji plotly pillow`
- 中文字体使用 `/System/Library/Fonts/PingFang.ttc`（macOS）
- 所有图表用中文标注
- 图表嵌入 HTML（base64），生成单文件报告
- 输出路径：`./chat_analysis_report.html`

---

## 第五步：生成深度情感分析报告

基础报告生成后，把下面这段发给 Claude Code：

---

**在基础报告基础上，生成一份深度情感分析的独立 HTML 报告。**

**数据配置同上（复用已确认的配置）。**

**深度分析维度：**

**1. 依恋与安全感**
- 主动发起对话次数（1小时空档后第一条）
- 连续发3条以上消息次数（等待回复的焦虑信号）
- 催促词频率（"在吗""怎么不回""宝宝？"等）
- 早安/晚安主动发送次数
- "想你"类情感表达次数对比
- 图表：依恋行为多维对比柱状图

**2. 沟通质量**
- 敷衍回复率（"嗯""哦""好""ok"等≤2字回复占比）
- 实质性消息率（≥20字消息占比）
- 白天(8-22点) vs 深夜(23-7点)：爱意词密度 vs 负面情绪密度
- 图表：沟通质量对比 + 白天/深夜情感密度对比

**3. 冲突模式**
- 找出周粒度消息量低于均值35%的时期
- 读取每个低谷期前后各4天的实际消息内容
- 判断：是冷战、是忙碌、还是见面了导致消息少
- 说明：真正的冷战特征是"消息极少且情绪对立"，要区分"因为见面所以不发消息"和"因为吵架所以不发消息"

**4. 感情里程碑还原**
- 搜索关键词："喜欢你""爱你""在一起""女朋友""男朋友""表白"
- 找出第一次互说"爱你"的具体时间和上下文
- 找出关系确立的大致时间
- 标注其他重要节点（第一次吵架、异地、毕业、工作等）
- 展示每个节点的实际聊天片段

**5. 成长轨迹**
- 按年度统计：平均消息长度、爱意词密度、深度话题密度（工作/未来/计划等词频）
- 图表：年度特征变化柱状图
- 情感基调全程变化曲线（标注关键里程碑）
- 文字分析：从相识到现在，聊天方式和话题深度如何演变

**6. 对未来的建议**
- 优势：稳定性、均衡性、共同经历
- 潜在风险：话题深度、沟通不对等、外部压力
- 3条具体可操作的建议

**输出要求：**
- 用叙述性语言，像朋友分析一样自然，不要只列数据
- 每个维度附上真实聊天记录截图（气泡样式）作为证据
- 最后写一封"给你们的信"：作为读了全部消息的旁观者，说真心话
- 深色背景信封样式，有温度
- 输出为独立 HTML 文件：`./deep_analysis_report.html`

---

## 注意事项

**关于数据隐私**
- 生成的 HTML 文件包含真实聊天内容，请妥善保管
- 不要上传到网络或分享给他人
- 分析完成后可以把临时脚本删除

**关于消息类型解码**
微信消息的 `local_type` 字段有大数字，是 type49（富媒体）的子类型，解码方式：
```python
def decode_msg_type(t):
    base = t % (2**32)
    sub  = t // (2**32)
    if base == 49:
        names = {1:'链接', 5:'链接分享', 6:'文件', 8:'位置',
                 19:'小程序', 33:'小程序', 57:'引用回复',
                 51:'视频号', 2000:'拍一拍'}
        return names.get(sub, f'富媒体({sub})')
    return {1:'文字', 3:'图片', 34:'语音', 43:'视频',
            47:'表情包', 10000:'系统消息'}.get(base, f'其他')
```

**关于 sender_id 跨库不一致**
每个 message_*.db 里"我"的 real_sender_id 可能不同（每个库不一样，需要分别确认），
需要分别确认，不能假设所有库里都是同一个 ID。

**关于字体**
- macOS: `/System/Library/Fonts/PingFang.ttc`
- Windows: `C:/Windows/Fonts/msyh.ttc`（微软雅黑）
- Linux: 需要手动下载中文字体

---

## 快速参考：我自己的项目配置（示例）

```python
# 示例配置（请替换为你自己的参数）
DB_BASE   = "/path/to/decrypted/message"
TABLE     = "Msg_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
MY_IDS    = {0: 1, 1: 1, 2: 1, 3: 1}  # key=DB编号, value=我的real_sender_id
HER_LABEL = "TA"
# DB0: 时间段1（消息数量）
# DB1: 时间段2（消息数量）
# DB2: 时间段3（消息数量）
# DB3: 时间段4（消息数量）
```

---

## 生成文件清单

完成后你会得到：

| 文件 | 说明 | 大小参考 |
|------|------|----------|
| `chat_analysis_report.html` | 基础可视化报告（12张图表） | ~2.4 MB |
| `deep_analysis_report.html` | 深度情感分析报告（含聊天气泡） | ~0.4 MB |
| `analyze_chat.py` | 基础报告生成脚本 | 可保留复用 |
| `deep_analysis.py` | 深度报告生成脚本 | 可保留复用 |

在手机上打开 HTML 文件的方式：
- **同一 WiFi 下**：Mac 运行 `cd /path/to/reports && python3 -m http.server 8080`，手机访问 `http://【Mac的局域网IP】:8080`
- **直接传输**：AirDrop 传到手机，用 Safari 打开（Chrome 也可以）

---

*Prompt 版本：2026-05 · 基于 wechat-decrypt 项目*
