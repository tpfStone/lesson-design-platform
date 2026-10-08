# OCR 安装与使用说明

> 适用场景：需要评阅**扫描版 PDF**（整页图片、无法选中文字）时，必须先安装 OCR 组件。
> 普通 Word 教案、文字版 PDF **不需要**安装 OCR。

---

## 一、先判断：我需要装 OCR 吗？

### 什么是扫描版 PDF？
把纸质教案**扫描/拍照**生成的 PDF —— 里面每一页都是**图片**，不是文字。

### 30 秒自测

| 判断方法 | 扫描版 PDF 的表现 |
|---------|-----------------|
| 打开 PDF，用鼠标**选中一段文字** | 选不中（整页像一张图）|
| 按 `Ctrl + F` 搜一个页面上能看到的词 | 搜不到 |
| 看系统的评分日志 | 出现 `ModuleNotFoundError: No module named 'easyocr'`，或提示需要 OCR |

> ✅ 只要你的教案是 **Word（.docx）** 或**文字版 PDF**，就**完全不需要**装 OCR，跳过本文档即可。

---

## 二、去哪安装

OCR 组件（`easyocr`）是一个 **Python 包**，通过 `pip` 从网上安装。

### 方式 A（推荐）：双击一键脚本

进入系统文件夹 → `tools` → 双击 **`install_ocr.bat`** → 按提示输入 `Y` 确认

脚本会自动：探测 Python → 用国内镜像安装 → 安装后自检

### 方式 B：手动命令行

在本系统文件夹里打开命令行（地址栏输入 `cmd` 回车），执行：

```bat
python -m pip install easyocr -i https://pypi.tuna.tsinghua.edu.cn/simple
```

> `-i https://pypi.tuna.tsinghua.edu.cn/simple` 是**清华镜像源**，国内下载快很多。
> 不加快可能非常慢甚至超时。

---

## 三、安装到哪（重要）

**easyocr 会安装到你运行本系统所用的那个 Python 环境里。**

### 怎么确认是哪个 Python？

**方法 1**：双击 `start_web.bat` 时，窗口开头会显示：
```
Python 版本：Python 3.12.0
```

**方法 2**：命令行执行：
```bat
python -c "import sys; print(sys.executable)"
```
会输出 Python 的完整路径，例如：
```
D:\python\python.exe
```

那么 easyocr 就会装到：
```
D:\python\Lib\site-packages\easyocr\
```

### ⚠️ 最常见的坑

如果你的电脑装了**多个 Python**（比如同时有 Anaconda、3.11、3.12），用 `pip install` 可能装到"另一个 Python"里，
于是系统启动时仍然提示找不到 easyocr。

**解决办法**：始终用 `python -m pip install ...`（而不是直接 `pip install ...`），
这样会**确保装到当前 `python` 命令对应的那个环境**。

---

## 四、安装时会下载什么（体积与耗时）

| 项目 | 说明 |
|------|------|
| easyocr 包本身（含 PyTorch） | **约 2 GB** |
| 首次**运行**时的识别模型 | 约 100–200 MB，自动下载到 `C:\Users\<你的用户名>\.EasyOCR\model` |
| 安装耗时 | 视网速 5–20 分钟 |
| 磁盘占用 | 约 2–3 GB |

> 所以：**只在确有扫描版教案要评时再装**，不需要就别装（省 2GB）。

---

## 五、怎么使用（装完要做什么）

### ✅ 不需要任何配置

系统检测到 easyocr 已安装后会**自动启用**，你不用改任何设置。

### 使用流程

```
上传扫描版 PDF → 系统自动做 OCR 识别 → 按识别出的文字评分批注
```

### 验证是否装好

命令行执行：
```bat
python -c "import easyocr; print('OCR 已就绪')"
```
看到 `OCR 已就绪` 即安装成功。

也可以直接跑一份扫描版 PDF：日志里会出现 OCR 相关提示，且能正常出评分结果。

### 耗时对比（心里有数）

| 教案类型 | 单份耗时 |
|---------|---------|
| Word / 文字版 PDF | 1–3 分钟 |
| **扫描版 PDF**（含 OCR） | **5–10 分钟**（取决于页数）|

---

## 六、常见问题

### Q1. 装完了，系统还是提示找不到 easyocr？

→ 装到了别的 Python。按第三节的方法确认 `python` 对应的路径，然后用
`python -m pip install easyocr -i https://pypi.tuna.tsinghua.edu.cn/simple` 重装。

### Q2. 下载特别慢 / 中途超时？

→ 确认命令里带了清华镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`；
网络不稳时可重试（pip 会续传部分包）。

### Q3. 提示 PyTorch 安装失败 / 磁盘空间不足？

→ easyocr 依赖 PyTorch（约 2GB）。请先清理磁盘（至少留 5GB 空闲）后重试。

### Q4. OCR 识别结果错字很多？

→ 与扫描质量有关：倾斜、模糊、手写的扫描件识别率低。建议用**清晰、正放**的扫描件；
识别不完美的部分，可结合「🔍 复核标注」功能人工修正。

### Q5. 装完能卸载吗？

→ 可以：
```bat
python -m pip uninstall easyocr torch torchvision -y
```

### Q6. 我以后不想用 OCR，会影响其他功能吗？

→ 不影响。不装 OCR 时，Word 与文字版 PDF 的评分批注功能完全正常。

---

## 七、一句话总结

| 问题 | 答案 |
|------|------|
| **去哪装** | 双击 `tools\install_ocr.bat`，或用 pip + 清华镜像 |
| **装到哪** | 装到运行本系统的那个 Python 环境（用 `python -m pip` 保证装对）|
| **怎么用** | 装完即用，无需配置；上传扫描版 PDF 会自动 OCR（单份 5–10 分钟）|
