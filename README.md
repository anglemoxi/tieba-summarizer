# 📝 贴吧楼主帖子汇总工具

输入一个贴吧帖子链接，自动抓取**楼主的全部发言**，生成带 AI 摘要的 Markdown 文件，方便离线阅读和存档。

---

## 🧑‍💻 小白从零开始教程（完全不会编程也能用）

跟着下面步骤走，大概 10 分钟搞定。

### 第一步：安装 Python

Python 是这个工具的运行环境，就像你要玩游戏得先装 Steam 一样。

1. 打开 [python.org](https://www.python.org/downloads/)
2. 点黄色大按钮 **Download Python** 下载安装包
3. 运行安装包，**‼️ 一定要勾选底部的 `Add Python to PATH`**（把 Python 加到系统路径），然后点 Install Now
4. 安装完成后，按键盘 `Win + R`，输入 `cmd` 回车，弹出黑窗口
5. 在黑窗口输入 `python --version` 回车，如果显示 `Python 3.x.x` 就说明装好了

### 第二步：下载这个工具

回到这个 GitHub 页面，点绿色的 **Code** 按钮 → **Download ZIP**，把压缩包下载到桌面。

下载完后：
1. 在桌面找到 `tieba-summarizer-main.zip`
2. 右键 → 解压到当前文件夹
3. 会得到一个 `tieba-summarizer-main` 文件夹

### 第三步：安装依赖

1. 打开 `tieba-summarizer-main` 文件夹
2. 在文件夹的**地址栏**里直接输入 `cmd` 然后回车，会弹出黑窗口
   > 或者：按住 `Shift` 键，在文件夹空白处右键 → "在此处打开 PowerShell 窗口"
3. 在黑窗口里依次输入以下命令（每输完一行按一次回车）：

```bash
pip install -r requirements.txt
```

等它跑完，出现 `Successfully installed...` 就 OK。

```bash
playwright install chromium
```

等它下载完浏览器内核（大概 100MB，只需下载一次）。

### 第四步：运行

仍然在黑窗口里，输入：

```bash
python main.py "贴吧帖子链接"
```

比如：

```bash
python main.py "https://tieba.baidu.com/p/8589589322"
```

它会自动抓取楼主的全部发言，生成一个 Markdown 文件放在 `output` 文件夹里。

> 💡 **如果报错"验证码"**：换成这个命令，会弹出一个浏览器窗口让你手动过验证：
> ```bash
> python main.py "https://tieba.baidu.com/p/1234567890" --visible --force-browser
> ```
> 验证通过后关掉浏览器，以后就不用再验证了。

### 第五步：查看结果

打开 `output` 文件夹，找到生成的 `.md` 文件。
- 可以用 **记事本** 打开
- 推荐用 [Typora](https://typora.io/) 或者 VS Code 打开，排版更好看

---

## 🚀 常用命令

```bash
# 基础抓取（自动尝试 AI 摘要）
python main.py "帖子链接"

# 只抓取不要摘要
python main.py "帖子链接" --no-summary

# 限制抓取 10 页
python main.py "帖子链接" --max-pages 10

# 第一次用，弹浏览器过验证码
python main.py "帖子链接" --visible --force-browser
```

---

## 🤖 开启 AI 摘要（可选）

如果想要自动生成帖子内容摘要，需要配置 Claude API Key：

1. 在项目文件夹里找到 `.env.example`，复制一份改名为 `.env`
2. 用记事本打开 `.env`，把 `sk-ant-xxxxxxxxxxxxx` 替换成你自己的 API Key：
   ```
   ANTHROPIC_API_KEY=sk-ant-你的真实key
   ```
3. 保存，搞定。以后每次抓取完会自动生成摘要。

> API Key 可以从 [console.anthropic.com](https://console.anthropic.com/) 获取（需要充值，不贵）。

---

## 🏗️ 项目结构

```
tieba-summarizer/
├── main.py              # 程序入口
├── config.py            # 配置（超时、延迟、UA 等）
├── parser.py            # 网页解析器
├── summarizer.py        # AI 摘要（Claude API）
├── writer.py            # Markdown 生成
├── fetcher/
│   ├── api_fetcher.py   # 方式1：API 抓取（最快）
│   ├── http_fetcher.py  # 方式2：HTTP 爬取
│   └── browser_fetcher.py # 方式3：浏览器抓取（兜底）
├── output/              # 输出文件在这
└── requirements.txt     # 依赖清单
```

### 抓取策略（自动降级）

| 优先级 | 方式 | 说明 |
|--------|------|------|
| ① | 贴吧内部 API | 最快，直接拿 JSON 数据 |
| ② | HTTP 网页爬取 | 中等，解析 HTML 页面 |
| ③ | 模拟浏览器 | 最稳，能过所有反爬，但最慢 |

三种方式会自动切换，用户不用管。

---

## ⚠️ 注意

- 内置了随机延迟（1~3 秒），不会狂刷贴吧服务器
- `.tieba_cookies.json` 存的是你百度登录态，**千万别上传到网上**
- 请仅用于个人阅读归档，遵守贴吧服务条款
- 如果抓取失败，大概率是百度弹验证码了，用 `--visible --force-browser` 手动过一下

---

## 📜 License

MIT
