# 08 内容解析 (openviking/parse)

## 1. 模块概览

`openviking/parse/` 实现了从多种来源获取原始数据、解析为结构化文档树、并将结果映射到 VikingFS URI 的完整管道。

| 子模块 | 用途 |
|---|---|
| `accessors/` | 数据访问层 (HTTP, Git, Feishu, Local) |
| `parsers/` | 文档解析器 (20+ 格式, 9 种代码语言 AST) |
| `resource_detector/` | 资源检测与分类 |
| `registry.py` | 解析器注册表单例 |
| `tree_builder.py` | 解析树 → VikingFS URI 映射 |
| `vlm.py` | VLM 文档处理器 (图像/表格/页面分析) |
| `directory_scan.py` | 目录扫描与文件分类 |
| `gitignore.py` | Gitignore 感知文件匹配 |
| `converter.py` | 文档转 PDF (LibreOffice/pandoc) |
| `custom.py` | 自定义解析器集成 |

---

## 2. 数据访问器 (accessors/)

### 2.1 抽象基类

```python
@dataclass
class LocalResource:
    path: Path               # 本地文件路径
    source_type: SourceType  # LOCAL / GIT / HTTP / FEISHU
    original_source: str     # 原始来源 URL/路径
    meta: Dict[str, Any]
    is_temporary: bool       # 是否需要清理
    
    def cleanup()            # 删除临时文件
    # 支持上下文管理器 (__enter__ / __exit__)

class DataAccessor(ABC):
    priority: int            # 优先级 (高→先匹配)
    
    @abstractmethod
    def can_handle(source) -> bool
    @abstractmethod
    async def access(source, **kwargs) -> LocalResource
```

### 2.2 访问器清单

| 访问器 | 优先级 | 处理来源 |
|---|---|---|
| `FeishuAccessor` | 100 | feishu.cn / larksuite.com / larkoffice.com URL |
| `GitAccessor` | 80 | git@, git://, ssh://, GitHub/GitLab HTTP URL, .git 路径 |
| `HTTPAccessor` | 50 | HTTP/HTTPS URL |
| `LocalAccessor` | 1 | 本地文件路径 (回退) |

### 2.3 HTTP 访问器

```python
class HTTPAccessor:
    async def access(source, **kwargs) -> LocalResource:
        # 1. 检测 URL 类型 (WEBPAGE / DOWNLOAD_PDF / DOWNLOAD_MD...)
        # 2. GitHub/GitLab blob URL → raw URL 转换
        # 3. 下载到临时文件 (正确扩展名)
        # 4. 错误分类: DNS / 连接 / 超时 / HTTP 错误

class URLTypeDetector:
    def detect(url) -> URLType:
        # 检查顺序: 扩展名 → Content-Disposition → Content-Type → 默认 WEBPAGE
        # Content-Disposition 支持: RFC 5987, 带引号字符串, 令牌
```

### 2.4 Git 访问器

```python
class GitAccessor:
    async def access(source, **kwargs) -> LocalResource:
        # 策略1: GitHub ZIP 下载 (通过 Archive API, 支持 GITHUB_TOKEN)
        # 策略2: GitLab ZIP 下载
        # 策略3: git clone (浅克隆 --depth 1 --recursive)
        # 提交检出: 多策略回退 (--branch + fetch origin <commit> + checkout)
        # Zip Slip 防护
```

---

## 3. 文档解析器 (parsers/)

### 3.1 抽象基类

```python
class BaseParser(ABC):
    supported_extensions: List[str]
    
    def can_parse(path) -> bool          # 检查扩展名
    
    @abstractmethod
    async def parse(source, instruction, **kwargs) -> ParseResult
    @abstractmethod
    async def parse_content(content, source_path, instruction, **kwargs) -> ParseResult
    
    # 公共方法:
    def _read_file(path) -> str            # 编码检测 (utf-8, gbk, shift_jis...)
    def _get_viking_fs() -> VikingFS       # 惰性单例
    def _create_temp_uri() -> str          # viking://temp/{random}
```

### 3.2 解析器清单

| 解析器 | 支持格式 | 实现方式 |
|---|---|---|
| `MarkdownParser` | .md, .markdown, .mdown, .mkd | 标题检测, Frontmatter, 智能分段, 段落合并 |
| `HTMLParser` | .html, .htm | readabilipy 提取 + markdownify 转换 → MarkdownParser |
| `PDFParser` | .pdf | 双策略: pdfplumber (本地) / MinerU (远程 API) |
| `WordParser` | .docx | python-docx, 标题/表格/内联格式保留 |
| `ExcelParser` | .xlsx, .xls, .xlsm | openpyxl / xlrd, 多工作表, 日期/错误/布尔处理 |
| `PowerPointParser` | .pptx | python-pptx, 标题/正文/备注提取 |
| `EPubParser` | .epub | ebooklib, HTML→Markdown 内联转换 |
| `LegacyDocParser` | .doc | OLE2 二进制解析 (Word 97+ 格式规范) |
| `ZipParser` | .zip | 安全解压 (Zip Slip 防护) → DirectoryParser |
| `DirectoryParser` | 目录 | 扫描→分类→逐文件处理→合并 |
| `CodeRepositoryParser` | Git/Zip 仓库 | 文件类型检测, gitignore 感知上传 |
| `FeishuParser` | 飞书 URL | 38 种块类型, 表格/Sheets/Bitable 支持 |
| `TextParser` | .txt, .text | 委托给 MarkdownParser |
| `ImageParser` | .png, .jpg, .gif, .webp, .svg | VLM 描述 + OCR (pytesseract) |
| `AudioParser` | .mp3, .wav, .ogg, .flac, .m4a | ASR (OpenAI Whisper, 含时间戳) |
| `VideoParser` | .mp4, .avi, .mov, .mkv | 占位符 (魔数验证) |

### 3.3 PDF 解析器详细

```python
class PDFParser:
    # 本地策略:
    def _convert_local():
        # 1. 提取书签 (pdfminer 大纲) → 标题结构
        # 2. 字体大小分析 (_detect_headings_by_font):
        #    - 采样所有页面字体大小
        #    - body = 最频繁大小
        #    - heading = body + delta (最大 max_heading_levels 级别)
        #    - 去重 >30% 页面出现的重复标题
        # 3. 表格提取 (Markdown 格式)
        # 4. 图像提取 (StoragePath + storage.save_image)
    
    # 远程策略:
    def _convert_mineru():
        # POST 上传到 MinerU API (Bearer 认证)
        # 可配置超时/参数
```

### 3.4 代码 AST 骨架提取 (parsers/code/ast/)

```python
def extract_skeleton(file_name, content, verbose=False) -> Optional[str]:
    """为代码文件提取 AST 骨架 (函数签名/类定义/导入)"""

# 支持的语言:
# Python (.py)        → PythonExtractor (tree-sitter-python)
# JavaScript (.js)    → JsTsExtractor (tree-sitter-javascript)
# TypeScript (.ts)    → JsTsExtractor (tree-sitter-typescript)
# Java (.java)        → JavaExtractor (tree-sitter-java)
# C/C++ (.c/.cpp/.h)  → CppExtractor (tree-sitter-cpp)
# Rust (.rs)          → RustExtractor (tree-sitter-rust)
# Go (.go)            → GoExtractor (tree-sitter-go)
# C# (.cs)            → CSharpExtractor (tree-sitter-c-sharp)
# PHP (.php)          → PhpExtractor (tree-sitter-php)
# Lua (.lua)          → LuaExtractor (tree-sitter-lua)

# 输出格式 (CodeSkeleton):
"""
Language: python

class MyClass(BaseClass):
    + method1(param1: str, param2: int) -> bool
        Docstring about this method.

def my_function(x: int, y: int) -> str

import os
from typing import List, Optional
"""
```

---

## 4. ParserRegistry - 解析器注册表

```python
class ParserRegistry:
    """单例, 扩展名→解析器映射"""
    
    def register(name, parser)           # 注册解析器
    def get_parser(name) -> BaseParser
    def get_parser_for_file(path) -> BaseParser  # 基于扩展名
    def parse(source, **kwargs) -> ParseResult   # 自动检测
    def register_custom(handler, extensions, name)  # 自定义解析器 (协议)
    def register_callback(extension, parse_fn, name)  # 基于函数
    def list_parsers() -> List[str]
    def list_supported_extensions() -> List[str]
```

---

## 5. VLMProcessor - VLM 文档处理器

```python
class VLMProcessor:
    async def understand_image(image, context, instruction) -> VLMResult
        # 使用提示词模板 vision.image_understanding
    
    async def understand_table(table, instruction) -> VLMResult
        # 表格结构分析
    
    async def understand_page(image, page_num, instruction) -> VLMResult
        # 页面内容分析
    
    async def batch_understand_pages(images, instruction, batch_size, max_concurrency) -> List[VLMResult]
        # 并发批处理 (Semaphore 控制)
    
    async def batch_analyze_document(title, reason, ...) -> DocumentAnalysisResult
        # 视觉或纯文本路径
        # 过滤有意义的图像 (filter_meaningful_images)
```

---

## 6. 资源检测器 (resource_detector/)

```python
class DetectInfo:
    visit_type: VisitType       # DIRECT_CONTENT / FILE_SYS / NEED_DOWNLOAD / READY_CONTEXT_PACK
    size_type: SizeType         # IN_MEM / EXTERNAL / TOO_LARGE_TO_PROCESS
    recursive_type: RecursiveType  # SINGLE / RECURSIVE / EXPAND_TO_RECURSIVE

class VisitType:
    DIRECT_CONTENT        # 直接文本内容
    FILE_SYS             # 文件系统 (目录)
    NEED_DOWNLOAD         # 需要下载 (URL)
    READY_CONTEXT_PACK    # 预打包上下文
```

---

## 7. 目录扫描 (directory_scan.py)

```python
def scan_directory(root, registry, strict, ignore_dirs, include, exclude) -> DirectoryScanResult:
    # 1. 遍历目录树
    # 2. 应用 gitignore 规则 (GitignoreMatcher)
    # 3. 分类文件: processable / unsupported / skipped
    # 4. include/exclude 模式匹配
    # 5. 返回分类结果

class GitignoreMatcher:
    def spec_for_dir(dir_path)           # 递归查找 .gitignore
    def is_ignored_file(file_path, spec) -> bool
    def is_ignored_dir(dir_path, spec) -> bool
```
