# 13 加密 & 隐私 (openviking/crypto, privacy)

## 1. 加密系统 (crypto/)

### 1.1 架构

```
RootKeyProvider (抽象)
├── LocalFileProvider         ← 本地主密钥文件
├── VaultProvider            ← HashiCorp Vault
└── VolcengineKMSProvider    ← 火山引擎 KMS
    ↓
FileEncryptor (信封加密)
    ↓
AES-256-GCM 加密/解密
```

### 1.2 信封加密 (encryptor.py)

```python
class FileEncryptor:
    """AES-256-GCM 信封加密"""
    
    def encrypt(account_id, plaintext: bytes) -> bytes:
        """
        1. 生成随机文件密钥 (32 字节)
        2. 生成数据 IV (12 字节)
        3. 使用 AES-256-GCM 加密明文
        4. 通过 RootKeyProvider 加密文件密钥
        5. 构建信封:
           ┌──────────────────────┐
           │ Magic: "OVE1"  (4B)  │
           │ Version       (2B)   │
           │ Provider Type (2B)   │
           │ EncKeyLen     (2B)   │
           │ KeyIVLen      (2B)   │
           ├──────────────────────┤
           │ EncryptedFileKey     │
           │ Key IV               │
           │ Data IV              │
           │ Encrypted Content    │
           └──────────────────────┘
        """
    
    def decrypt(account_id, ciphertext: bytes) -> bytes:
        """
        1. 检查 Magic 前缀 (无前缀 → 明文直通)
        2. 解析信封头部
        3. 通过 RootKeyProvider 解密文件密钥
        4. 使用 AES-256-GCM 解密内容
        """
    
    # 所有操作都记录指标 (操作计数, 有效载荷大小, 认证失败)
```

### 1.3 密钥提供者 (providers.py)

```python
class RootKeyProvider(ABC):
    """根密钥提供者抽象"""
    
    @abstractmethod
    def get_root_key() -> bytes
    @abstractmethod
    def derive_account_key(account_id) -> bytes  # HKDF-SHA256 派生
    @abstractmethod
    def encrypt_file_key(plaintext_key, account_id) -> bytes
    @abstractmethod
    def decrypt_file_key(encrypted_key, iv, account_id) -> bytes

class LocalFileProvider(RootKeyProvider):
    """~/.openviking/master.key (0600 权限)"""
    # 不存在时自动创建 (secrets.token_bytes(32), hex 编码)
    # 通过 HKDF 派生账户密钥
    # 缓存根密钥

class VaultProvider(RootKeyProvider):
    """HashiCorp Vault (Transit Secrets Engine)"""
    # Transit 密钥: AES256-GCM96
    # 加密的根密钥存储在 KV Secrets Engine (v1/v2)
    # 通过 hvac 客户端通信
    # 自动激活 Transit Engine

class VolcengineKMSProvider(RootKeyProvider):
    """火山引擎 KMS"""
    # KMS Encrypt/Decrypt 操作
    # 加密的根密钥: ~/.openviking/openviking-volcengine-root-key.enc
    # 通过 volcengine SDK (SignerV4 认证)
```

### 1.4 配置 (config.py)

```python
def validate_encryption_config(config) -> None:
    """验证加密配置完整性"""
    # 检查: enabled, provider 类型, 提供商特定字段

def bootstrap_encryption(config) -> FileEncryptor:
    """从配置创建加密器"""
    # 1. 验证配置
    # 2. 创建提供者
    # 3. 返回 FileEncryptor

def encryption_health_check(config) -> bool:
    """测试加密/解密往返"""
```

### 1.5 异常层次

```python
EncryptionError              # 基类
├── InvalidMagicError        # 魔数不匹配
├── CorruptedCiphertextError # 密文损坏
├── AuthenticationFailedError# GCM 认证失败
├── KeyMismatchError         # 密钥不匹配
├── KeyNotFoundError         # 密钥未找到
├── ConfigError              # 配置错误
└── KMSError                 # KMS 错误
```

---

## 2. 隐私系统 (privacy/)

### 2.1 核心概念

OpenViking 隐私系统提供**版本化的用户隐私配置**和**技能敏感值自动提取与替换**。

### 2.2 数据模型 (models.py)

```python
@dataclass
class UserPrivacyConfigMeta:
    category: str              # 配置分类
    target_key: str            # 目标键 (如 "api_keys", "credentials")
    active_version: int        # 当前活跃版本号
    latest_version: int        # 最新版本号
    created_at: str
    updated_at: str
    updated_by: str
    labels: Dict[str, str]

@dataclass
class UserPrivacyConfigVersion:
    version: int
    category: str
    target_key: str
    values: Dict               # 敏感键值对
    created_at: str
    created_by: str
    change_reason: str
```

### 2.3 存储路径 (helpers.py)

```python
# URI 结构:
# viking://user/{space}/privacy/{category}/{target_key}/
#   ├── meta.json
#   ├── current.json
#   └── history/
#       ├── version_001.json
#       ├── version_002.json
#       └── ...

def config_root_uri(user_space, category, target_key) -> str
def current_uri() -> str
def version_uri(version) -> str
def version_filename(version) -> str  # 零填充宽度 3
```

### 2.4 配置服务 (service.py)

```python
class UserPrivacyConfigService:
    """版本化隐私配置 CRUD"""
    
    async def upsert(ctx, category, target_key, values, updated_by, change_reason) -> None:
        # 如果值未变化 → 无操作
        # 递增版本号
        # 写入 version_{N}.json + current.json
    
    async def get_current(ctx, category, target_key) -> Dict
    async def get_version(ctx, category, target_key, version) -> Dict
    async def list_versions(ctx, category, target_key) -> List[int]
    async def list_categories(ctx) -> List[str]
    async def list_targets(ctx, category) -> List[str]
    
    async def activate_version(ctx, category, target_key, version, updated_by) -> None:
        # 将快照复制到 current.json
```

### 2.5 技能隐私提取 (skill_extractor.py)

```python
@dataclass
class SkillPrivacyExtractionResult:
    values: Dict               # 提取的敏感值
    original_content: str      # 原始内容
    sanitized_content: str     # 清理后的内容
    original_content_blocks: List[str]
    replacement_content_blocks: List[str]

async def extract_skill_privacy_values(skill_name, skill_description, content):
    """
    1. 使用 VLM + 隐私提取提示词模板
    2. parse_json_from_response → 值字典
    3. placeholderize_skill_content_with_blocks → 替换
    """
```

### 2.6 占位符替换 (skill_placeholder.py)

```python
# 占位符格式: {{ov_privacy:skill:{skill_name}:{field_name}}}

def build_placeholder(skill_name, field_name) -> str:
    return f"{{{{ov_privacy:skill:{skill_name}:{field_name}}}}}"

def placeholderize_skill_content(content, skill_name, values) -> str:
    """
    用占位符替换敏感值
    - 按值长度降序 (防部分替换)
    - 12 种上下文感知替换模式 (引号/等号/冒号分隔)
    """
```

### 2.7 占位符恢复 (skill_restore.py)

```python
def get_skill_name_from_uri(uri) -> str:
    # 从 VikingFS URI 提取技能名称

def restore_skill_content(content, skill_name, values) -> str:
    """
    读取时恢复占位符
    - 正则提取所有 {{ov_privacy:skill:{name}:{field}}}
    - 用实际值替换
    - 附加 [Privacy Config Notice] 用于未配置的值
    """
```
