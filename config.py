# ============================================================
# config.py  ——  主要修改这个文件来改变爬取目标
# ============================================================
# 改完这里，直接运行：  python3 run.py
# 不用动其他脚本（除非你要加新字段，见教程.md）
# ============================================================

# ---------- 基础设置 ----------
BASE_URL = 'https://cn.iherb.com'   # 中文站；英文站改成 https://www.iherb.com
LOCALE   = 'zh-CN'                  # 页面语言（影响返回的是中文还是英文）

# ---------- 爬取模式 ----------
# 'keyword' = 按品类/原料关键词爬取（已实现并验证）
# 'brand'   = 按品牌爬取（用下面的 BRAND_FILTER，或见教程里的品牌页方案）
MODE = 'keyword'

# ---------- 搜索关键词（改这里切换品类）----------
# 单个品类：
#   KEYWORDS = ['collagen']
# 多个品类批量跑（每个关键词独立翻页）：
#   KEYWORDS = ['collagen', 'vitamin c', 'omega-3', 'probiotics', 'magnesium']
KEYWORDS = ['CoQ10']

# ---------- 品牌过滤（可选，留空 = 不过滤）----------
# 只在搜索结果里保留匹配的品牌。支持模糊匹配（包含即保留）。
# 例：BRAND_FILTER = ['NOW Foods', 'California Gold Nutrition', 'Sports Research']
BRAND_FILTER = []

# ---------- 爬取控制（防封 + 限速）----------
MAX_PAGES    = 1     # 每个关键词最多翻几页（每页约 48 个商品）
PAGE_DELAY   = 3     # 搜索页翻页之间的延迟（秒）
DETAIL_DELAY = 2     # 每个商品详情页之间的延迟（秒）
CF_WAIT      = 12    # Cloudflare 验证等待时间（秒，仅在首次/触发验证时需要）

# ---------- 测试用限制（正式跑设回 0）----------
DETAIL_LIMIT = 0     # 0 = 爬全部详情；N = 只爬前 N 个商品详情（快速验证用）

# ---------- 输出 ----------
OUTPUT_DIR = 'output'                 # 输出目录
CSV_NAME   = 'iherb_products.csv'      # 商品级 CSV 文件名
