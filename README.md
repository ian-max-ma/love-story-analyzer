# 💕 Love Story Analyzer

> 微信聊天记录解密 + 深度情感分析，生成两份可视化 HTML 报告。

## 包含内容

| 文件 | 说明 |
|------|------|
| `WECHAT_ANALYSIS_PROMPT.md` | **完整指南**：从解密数据库到生成报告的全流程 Prompt，复制给 Claude Code 即可 |
| `analyze_chat.py` | 基础可视化报告脚本（词云、情感趋势、热力图等） |
| `deep_analysis.py` | 深度情感分析脚本（依恋模式、冲突追踪、感情里程碑、给你们的信） |

## 快速开始

### 1. 解密微信数据库

参见 `WECHAT_ANALYSIS_PROMPT.md` 第一步。依赖 [wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt) 工具。

### 2. 安装依赖

```bash
pip3 install jieba wordcloud matplotlib pandas numpy snownlp emoji plotly pillow
```

### 3. 修改配置后运行

在 `analyze_chat.py` 和 `deep_analysis.py` 顶部修改：

```python
DB_BASE = "/path/to/decrypted/message"   # 解密后的数据库路径
TABLE   = "Msg_xxxxxxxxxxxxxxxxxxxxxxxx"  # 消息表名（32位MD5）
MY_IDS  = {0: 9, 1: 16, 2: 98, 3: 1}    # 各DB中"我"的 real_sender_id
```

然后：

```bash
python3 analyze_chat.py      # → chat_analysis_report.html
python3 deep_analysis.py     # → deep_analysis_report.html
```

### 4. 在手机上查看

```bash
# 与手机连同一 WiFi，Mac 上运行：
python3 -m http.server 8080
# 手机浏览器访问 http://【Mac局域网IP】:8080
```

## 报告预览

- **基础报告**：12 张图表，含每月消息趋势、词云、热力图、情感分析
- **深度报告**：6 个分析维度 + 真实聊天气泡 + 一封给你们的信

## ⚠️ 隐私提示

生成的 HTML 文件包含真实聊天内容，请妥善保管，不要上传到网络。

---

*基于 [wechat-decrypt](https://github.com/ylytdeng/wechat-decrypt) 项目*
