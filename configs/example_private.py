"""
私有配置模板 - configs/example_private.py
==========================================
将本文件复制为 configs/private.py 并填写实际值。

推荐使用 .env 文件配置（更简洁，无需改 Python 代码）：
  cp .env.example .env  然后编辑 .env 填写实际值即可。

此文件是 Python 配置方式（向后兼容），private.py 已加入 .gitignore。
"""

# ============================================================================
# LLM API（必填）
# 支持任何 OpenAI 兼容接口：Qwen / DeepSeek / OpenAI / 本地 Ollama 等
# ============================================================================

OPENAI_API_KEY  = "sk-your-api-key-here"
OPENAI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 其他常用端点（取消注释即可切换）：
# OPENAI_BASE_URL = "https://api.deepseek.com/v1"           # DeepSeek
# OPENAI_BASE_URL = "https://api.openai.com/v1"             # OpenAI

# LLM 模型名称（默认 deepseek-v3.1，可在此覆盖）
# LLM_MODEL = "qwen-plus"

# ============================================================================
# 数据路径（必填）
# ============================================================================

# 数据集父目录（AquaFetch 会在此目录下找 CAMELS_US/ 等子文件夹）
# 例：数据在 D:\data\CAMELS_US\ 则填 D:\data
DATASET_DIR = r"D:\your\path\to\data"

# 率定结果输出目录
RESULT_DIR  = r"D:\your\path\to\results"

# 项目根目录（可选，留空则自动推断）
PROJECT_DIR = r"D:\your\path\to\HydroAgent"

# hydrodataset NetCDF 缓存目录（可选，留空则默认为 DATASET_DIR 父目录下的 cache）
# HydroAgent 启动时自动写入 ~/hydro_setting.yml，无需手动配置。
CACHE_DIR = r""

