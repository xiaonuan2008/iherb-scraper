# iHerb 竞品爬虫（命令行版）

> 爬取 iHerb 竞品的商品信息、成分表、含量、UPC 等，导出 CSV。
> 适合功能食品 / 膳食补充剂研发的竞品调研与原料知识库建设。

## 功能特性

- 按品类关键词 / 品牌批量爬取
- 成分表结构化提取（成分名 + 含量 + 每日值%）
- 自动绕过 Cloudflare（Playwright 真实浏览器，无需登录 / 验证码）
- 每请求独立浏览器会话，规避连续请求限流
- 导出商品级 + 成分级两份 CSV

## 环境要求

- Python 3.10+
- 依赖安装：`pip install playwright beautifulsoup4`
- 浏览器安装：`playwright install chromium`

## 快速开始

```bash
pip install playwright beautifulsoup4
playwright install chromium
cd iherb_scraper
python3 run.py
```

## 配置（config.py）

| 配置项 | 说明 |
|--------|------|
| `KEYWORDS` | 搜索关键词列表，如 `['collagen', 'vitamin c']` |
| `BRAND_FILTER` | 品牌过滤（模糊匹配），留空 = 不过滤 |
| `MAX_PAGES` | 每关键词最多翻页数（每页约 48 个商品） |
| `DETAIL_LIMIT` | `0` = 全量；`N` = 只爬前 N 个（测试用） |
| `PAGE_DELAY` / `DETAIL_DELAY` | 翻页 / 详情延迟（秒），防封 |

## 输出（output/）

| 文件 | 内容 |
|------|------|
| `iherb_products.csv` | 商品级：名称 / 品牌 / 价格 / 规格 / UPC / 成分摘要 / 过敏原 … |
| `iherb_ingredients.csv` | 成分级：成分名 / 含量 / 每日值%，通过 `product_id` 关联 |

## 目录结构

```
iherb_scraper/
├── config.py          # 爬取配置（主要改这里）
├── run.py             # 运行入口
├── iherb_scraper.py   # 浏览器封装 + 页面解析 + 导出
├── 教程.md            # 详细使用教程
├── README.md          # 本文件
└── output/            # 结果 CSV（运行时生成）
```

## 注意事项

- iHerb 有 Cloudflare 反爬，已用浏览器自动过；请勿高频爬取（保持默认延迟）
- 成分表均为文字结构化数据，绝大多数无需 OCR
- 仅供个人竞品调研与学习使用，遵守目标网站 robots 与条款

## License

MIT
