# 双语字幕工具箱 (BISS)

![双语字幕工具箱 Logo](images/biss-logo.png)

一个功能强大的双语字幕制作工具，支持从视频文件和独立字幕文件创建双语字幕。支持中英、日英、韩英等多种语言组合，具备自动语言检测、智能轨道选择和时间轴对齐功能。

**[GitHub 主仓库](https://github.com/Deenyoro/Bilingual-Subtitle-Suite)** | **[English Documentation](https://github.com/Deenyoro/Bilingual-Subtitle-Suite/blob/master/README.md)**

## 下载

从 [GitHub Releases](https://github.com/Deenyoro/Bilingual-Subtitle-Suite/releases/latest) 下载最新版本。

| 文件 | 说明 | 大小 |
|------|------|------|
| **`biss.exe`** | 精简版 — 包含所有功能（PGS OCR 除外） | ~20 MB |
| **`biss-full.exe`** | 完整版 — 包含 PGS OCR 和 Tesseract 数据（eng, chi_sim, chi_tra, jpn, kor） | ~110 MB |

> **应该下载哪个版本？**
> 大多数用户应下载 **`biss.exe`**（精简版）。它支持字幕合并、对齐、编码转换、批量处理以及完整的 GUI/CLI 界面。仅当需要通过 OCR 转换 PGS（蓝光影像）字幕时，才需要下载 **`biss-full.exe`**。

## 效果展示

![双语字幕效果示例](images/biss-fma03.png)
*BISS 制作的中英双语字幕*

## 功能特性

### 双语字幕制作
- **自动语言检测**：从文件名和内容分析中识别语言
- **智能轨道选择**：区分主对话和强制/标牌字幕轨道
- **时间轴对齐**：自动处理轨道之间的时间差异
- **翻译辅助匹配**：可选 Google Cloud Translation API 进行语义对齐
- **多语言支持**：中文、日文、韩文与英文配对

### 处理能力
- **视频容器支持**：从 MKV、MP4、AVI、MOV、WebM、TS 中提取内嵌字幕
- **字幕格式**：SRT、ASS/SSA、VTT 输入输出
- **PGS 转换**：基于 OCR 的图像字幕转换（完整版或系统 Tesseract）
- **编码转换**：自动检测并转换为 UTF-8
- **时间轴调整**：按偏移量移动字幕或设定起始时间
- **批量处理**：单条命令处理整个目录

### 用户界面
- **图形界面**：全功能 GUI，支持拖放、预览和可视化反馈
- **命令行**：可脚本化的 CLI，选项丰富
- **交互模式**：菜单驱动的文本界面，引导操作流程

## 多语言界面

```bash
biss --lang zh          # 中文界面
biss --lang ja          # 日本語インターフェース
biss --lang ko          # 한국어 인터페이스biss --lang en          # English interface
```

应用会自动检测系统语言。设置环境变量 `BISS_LANG=zh` 可永久选择中文界面。

## 从源码安装

> **注意：** 如果您从 [Releases](https://github.com/Deenyoro/Bilingual-Subtitle-Suite/releases/latest) 页面下载了预编译的 exe 文件，请跳过此部分。直接运行 exe 即可，无需安装 Python。

### 系统要求
- Python 3.8 或更高版本（推荐 3.10+）
- 已安装 FFmpeg 并添加到 PATH
- Git（用于克隆仓库）

### 安装步骤
```bash
git clone https://github.com/Deenyoro/Bilingual-Subtitle-Suite.git
cd chsub
pip install -r requirements.txt

# 验证安装
biss --version
# 从源码运行：
python biss.py --version
```

### 可选：PGS 字幕转换
```bash
biss setup-pgsrip install
```

## 使用方法

> **从源码运行？** 将下文中的 `biss` 替换为 `python biss.py`。

### 图形界面（推荐新手使用）
```bash
biss gui
# 或直接：
biss
```

GUI 提供：
- 合并、调整、转换和批量操作的选项卡界面
- Ctrl+P 文件预览
- 自动语言检测标签
- 快速偏移按钮
- 实时操作日志

### 命令行

**合并两个字幕文件：**
```bash
biss merge chinese.srt english.srt
```
自动从文件名（.zh、.chi、.en、.eng 等）或内容检测语言。

**从视频提取并合并：**
```bash
biss merge movie.mkv
```
提取内嵌的中英字幕轨道并创建双语输出。

**调整字幕时间轴：**
```bash
# 后移 2.5 秒
biss shift subtitle.srt --offset="-2.5s"

# 前移 500 毫秒
biss shift subtitle.srt --offset 500ms
```

**转换编码：**
```bash
biss convert subtitle.srt
```
自动检测编码并转换为 UTF-8。

**批量操作：**
```bash
# 合并目录中所有视频
biss batch-merge "Season 01" --auto-confirm

# 将所有字幕转换为 UTF-8
biss batch-convert /path/to/subtitles --recursive
```

### 交互模式
```bash
biss interactive
```
提供菜单驱动的界面，引导完成所有操作。

## 高级选项

### 时间轴不一致时的对齐
```bash
biss merge movie.mkv --auto-align
```

大偏移量（50+ 秒）：
```bash
biss merge movie.mkv --auto-align --alignment-threshold 0.3
```

翻译辅助跨语言匹配：
```bash
biss merge movie.mkv --auto-align --use-translation
```

### 轨道选择
```bash
# 列出可用轨道
biss merge movie.mkv --list-tracks

# 指定轨道 ID
biss merge movie.mkv --chinese-track 3 --english-track 5

# 优先使用外部文件
biss merge movie.mkv --prefer-external
```

## 支持的格式

| 类型 | 格式 |
|------|------|
| 视频 | MKV、MP4、AVI、M4V、MOV、WebM、TS、MPG、MPEG |
| 字幕 | SRT、ASS、SSA、VTT |
| 编码 | UTF-8、UTF-16、GB18030、GBK、Big5、Shift-JIS 等 |
| 语言 | 中文（简体/繁体）、英文、日文、韩文 |

## 配置

### 环境变量
```bash
# Google Translation API 密钥（可选，用于 --use-translation）
export GOOGLE_TRANSLATE_API_KEY="your-api-key"

# FFmpeg 超时时间（秒，默认 900）
export FFMPEG_TIMEOUT=1800

# 界面语言
export BISS_LANG=zh
```

## 常见问题

**找不到 FFmpeg：**
安装 FFmpeg 并确保已添加到系统 PATH。使用 `ffmpeg -version` 测试。

**编码检测失败：**
```bash
pip install charset-normalizer
```

**输出乱码：**
```bash
biss convert subtitle.srt --force
```

**合并后时间轴不一致：**
```bash
biss merge file1.srt file2.srt --auto-align
```

### 调试模式
```bash
biss --debug merge movie.mkv
```

## 作者

Dean Thomas ([@Deenyoro](https://github.com/Deenyoro))

## 致谢

本项目集成了以下优秀的开源工具：

- **[PGSRip](https://github.com/ratoaq2/pgsrip)** by ratoaq2 — PGS 字幕提取（Apache 2.0）
- **[Tesseract OCR](https://github.com/tesseract-ocr/tesseract)** — 光学字符识别（Apache 2.0）
- **[FFmpeg](https://ffmpeg.org/)** — 音视频处理（LGPL/GPL）
