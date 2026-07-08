# ============================================================
# iherb_scraper.py  ——  核心爬取逻辑（一般不用改）
# ============================================================
# 包含：浏览器封装 / 搜索页解析 / 详情页解析 / 数据导出
# 需要改字段时，看本文件里的 _parse_search / _parse_detail
# ============================================================

import re
import os
import csv
import json
import asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

import config


class IHerbScraper:
    """iHerb 爬虫主类，封装浏览器与解析逻辑

    关键策略：Cloudflare 对「同一 session 连续请求」会触发 rate-based 中文
    挑战页（headless 下不放行）。实测发现「每个请求用全新 context（新
    session）」即可稳定通过——因为新 session 的首个请求必然放行。
    """

    UA = (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )

    def __init__(self):
        self.pw = None
        self.browser = None

    # ---------- 浏览器生命周期 ----------
    async def start(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled'],
        )

    async def close(self):
        await self.browser.close()
        await self.pw.stop()

    # ---------- 导航（每次新 context，自动过 Cloudflare）----------
    @staticmethod
    def _is_challenge(content):
        """识别 Cloudflare 验证页（中英文标题都会命中）"""
        markers = [
            'Just a moment',
            '请稍候',
            'challenges.cloudflare.com',
            '__cf_chl',
            'cf_chl_opt',
        ]
        return any(m in content for m in markers)

    async def _fetch(self, url):
        """每次请求开新 context（新 session），规避连续请求限流"""
        ctx = await self.browser.new_context(
            user_agent=self.UA,
            locale=config.LOCALE,
            viewport={'width': 1920, 'height': 1080},
        )
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(4000)  # 首请求通常已自动放行
            content = await page.content()
            # 保险：若仍卡挑战页，再等一轮
            if self._is_challenge(content):
                print('    ⚠ 触发挑战页，等待重试...')
                await page.wait_for_timeout(config.CF_WAIT * 1000)
                content = await page.content()
            return content
        finally:
            await ctx.close()
        if self._is_challenge(content):
            await self.page.wait_for_timeout(config.CF_WAIT * 1000)
            content = await self.page.content()
            if self._is_challenge(content):
                await self.page.wait_for_timeout(config.CF_WAIT * 1000)
                content = await self.page.content()
        return content

    # ---------- 搜索页 ----------
    async def scrape_search(self, keyword, max_pages):
        """翻页爬搜索结果，返回商品字典列表"""
        products = {}
        for p in range(1, max_pages + 1):
            url = f'{config.BASE_URL}/search?kw={keyword.replace(" ", "+")}&p={p}'
            print(f'  [搜索] 第 {p} 页: {url}')
            content = await self._fetch(url)
            page_products = self._parse_search(content)
            for pid, prod in page_products.items():
                products[pid] = prod
            print(f'  [搜索] 本页 {len(page_products)} 个，累计 {len(products)} 个')
            if len(page_products) < 48:
                break  # 已是最后一页
            await asyncio.sleep(config.PAGE_DELAY)
        return list(products.values())

    def _parse_search(self, html):
        """解析搜索页商品卡片（数据直接挂在 data-* 属性上）"""
        soup = BeautifulSoup(html, 'html.parser')
        links = soup.find_all('a', attrs={'data-product-id': True})
        products = {}
        for link in links:
            pid = link.get('data-product-id')
            if pid in products:
                continue
            raw_url = link.get('href', '')
            url = raw_url if raw_url.startswith('http') else config.BASE_URL + raw_url
            prod = {
                'product_id': pid,
                'part_number': link.get('data-part-number', ''),
                'brand': link.get('data-ga-brand-name', ''),
                'brand_id': link.get('data-ga-brand-id', ''),
                'price': link.get('data-ga-discount-price', ''),
                'title': link.get('title', ''),
                'url': url,
                'is_out_of_stock': link.get('data-ga-is-out-of-stock', ''),
                'position': link.get('data-ga-product-position', ''),
            }
            parent = link.find_parent('div', class_='product')
            if parent:
                sales = parent.find(string=re.compile(r'已售出|在.*天'))
                if sales:
                    prod['sales_text'] = sales.strip()
                rating_el = parent.find(attrs={'itemprop': 'ratingValue'})
                if rating_el:
                    prod['rating'] = rating_el.get('content', rating_el.get_text(strip=True))
                rc_el = parent.find(attrs={'itemprop': 'reviewCount'})
                if rc_el:
                    prod['review_count'] = rc_el.get('content', rc_el.get_text(strip=True))
                img = parent.find('img')
                if img:
                    prod['image_url'] = img.get('src') or img.get('data-src', '')
            products[pid] = prod
        return products

    # ---------- 详情页 ----------
    async def scrape_detail(self, product):
        content = await self._fetch(product['url'])
        return self._parse_detail(content, product)

    def _parse_detail(self, html, product):
        """解析商品详情页：JSON-LD + 成分表 + 其他信息"""
        soup = BeautifulSoup(html, 'html.parser')

        # 1) JSON-LD 结构化数据（最稳定）
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
            except Exception:
                continue
            if isinstance(data, dict) and data.get('@type') == 'Product':
                product['gtin12'] = data.get('gtin12', '')
                product['sku'] = data.get('sku', '')
                cat = data.get('category', {})
                product['category'] = cat.get('name', '') if isinstance(cat, dict) else cat
                w = data.get('weight', {})
                product['weight_value'] = w.get('value', '') if isinstance(w, dict) else ''
                product['weight_unit'] = w.get('unitText', '') if isinstance(w, dict) else ''
                ar = data.get('aggregateRating', {})
                if isinstance(ar, dict):
                    product['rating'] = ar.get('ratingValue', product.get('rating', ''))
                    product['review_count'] = ar.get('reviewCount', product.get('review_count', ''))
                product['description'] = data.get('description', '')
                product['jsonld_image'] = data.get('image', '')
                off = data.get('offers', {})
                if isinstance(off, dict):
                    product['price'] = off.get('price', product.get('price', ''))
                    product['currency'] = off.get('priceCurrency', '')
                    product['availability'] = off.get('availability', '').replace('https://schema.org/', '')
                break

        # 2) 成分表（supplement-facts-container 内的表格）
        facts = self._parse_supplement_facts(soup)
        if facts:
            product.update(facts)
        else:
            product['has_amount'] = False
            product['needs_ocr'] = True
            product['ingredients'] = []
            product['serving_size'] = ''
            product['servings_per_container'] = ''

        # 3) 其他成分 / 过敏原 / 注意事项
        product['other_ingredients'] = self._extract_section(soup, ['其他成分', 'Other Ingredients'])
        product['allergens'] = self._extract_section(soup, ['含：', 'Contains'])
        product['warnings'] = self._extract_section(soup, ['注意事项', 'Warnings'])

        # 4) 标签图片（/r/ 类型 = 标签细节图，作为 OCR 备份）
        product['label_images'] = self._extract_label_images(soup, product)

        return product

    def _parse_supplement_facts(self, soup):
        """解析成分表表格 → 结构化成分列表"""
        container = soup.find('div', class_='supplement-facts-container')
        if not container:
            return None
        table = container.find('table')
        if not table:
            return None
        rows = table.find_all('tr')
        serving_size = None
        servings_per_container = None
        ingredients = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
            text = ' '.join(cells)
            if not text.strip():
                continue
            if '每次用量' in text:
                m = re.search(r'每次用量[：:]\s*(.+)', text)
                serving_size = m.group(1).strip() if m else text
                continue
            if '每件包装服用次数' in text or 'servings' in text.lower():
                m = re.search(r'次数[：:]\s*(.+)', text) or re.search(r'约\s*(.+)', text)
                servings_per_container = m.group(1).strip() if m else text
                continue
            if len(cells) >= 2 and cells[0] and cells[0] not in ('补剂成分表', '每份含量'):
                name = cells[0]
                if name in ('每日摄入量百分比',):
                    continue
                amount = cells[1] if len(cells) > 1 else ''
                dv = cells[2] if len(cells) > 2 else ''
                if name:
                    ingredients.append({'name': name, 'amount': amount, 'daily_value': dv})
        if not ingredients:
            return None
        return {
            'serving_size': serving_size,
            'servings_per_container': servings_per_container,
            'ingredients': ingredients,
            'has_amount': any(i['amount'] for i in ingredients),
            'needs_ocr': False,
        }

    def _extract_section(self, soup, keywords):
        """按关键词找文本区块（其他成分/过敏原/注意事项）"""
        node = soup.find(string=lambda t: t and any(kw in t for kw in keywords))
        if not node:
            return ''
        parent = node.parent
        for _ in range(2):
            if parent.parent and len(parent.get_text(strip=True)) < 600:
                parent = parent.parent
        return parent.get_text(' ', strip=True)

    def _extract_label_images(self, soup, product):
        """提取标签细节图（/r/ 类型），用于无文字含量时 OCR"""
        folder = None
        img_src = product.get('jsonld_image', '') or product.get('image_url', '')
        m = re.search(r'images/([a-z]{3}/[a-z0-9]+)/', img_src)
        if m:
            folder = m.group(1)
        seen = set()
        result = []
        for img in soup.find_all('img', src=True):
            src = img['src']
            if folder and f'images/{folder}/r/' in src and src not in seen:
                seen.add(src)
                result.append(src)
        return result


# ============================================================
# 导出函数（CSV）
# ============================================================
def export(products, out_dir, csv_name):
    os.makedirs(out_dir, exist_ok=True)

    product_cols = [
        'product_id', 'part_number', 'brand', 'brand_id', 'title',
        'price', 'currency', 'gtin12', 'sku', 'category',
        'weight_value', 'weight_unit', 'rating', 'review_count',
        'serving_size', 'servings_per_container', 'has_amount', 'needs_ocr',
        'other_ingredients', 'allergens', 'warnings',
        'sales_text', 'is_out_of_stock', 'url', 'image_url', 'label_images',
    ]
    prod_path = os.path.join(out_dir, csv_name)
    with open(prod_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=product_cols, extrasaction='ignore')
        w.writeheader()
        for p in products:
            row = {}
            for k in product_cols:
                v = p.get(k, '')
                if isinstance(v, list):  # label_images 列表 → 分号分隔字符串
                    v = '; '.join(v)
                row[k] = v
            w.writerow(row)

    ing_cols = ['product_id', 'brand', 'title', 'ingredient_name', 'amount', 'daily_value', 'serving_size']
    ing_path = os.path.join(out_dir, 'iherb_ingredients.csv')
    with open(ing_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=ing_cols)
        w.writeheader()
        for p in products:
            for ing in p.get('ingredients', []):
                w.writerow({
                    'product_id': p.get('product_id', ''),
                    'brand': p.get('brand', ''),
                    'title': p.get('title', ''),
                    'ingredient_name': ing.get('name', ''),
                    'amount': ing.get('amount', ''),
                    'daily_value': ing.get('daily_value', ''),
                    'serving_size': p.get('serving_size', ''),
                })

    print(f'  ✓ 商品数据: {prod_path}')
    print(f'  ✓ 成分数据: {ing_path}')


# ============================================================
# 主流程
# ============================================================
async def run():
    all_products = []
    scraper = IHerbScraper()
    await scraper.start()
    try:
        for kw in config.KEYWORDS:
            print(f'\n=== 关键词: {kw} ===')
            products = await scraper.scrape_search(kw, config.MAX_PAGES)

            # 品牌过滤
            if config.BRAND_FILTER:
                products = [
                    p for p in products
                    if any(bf.lower() in p['brand'].lower() for bf in config.BRAND_FILTER)
                ]
                print(f'  [过滤] 品牌匹配后 {len(products)} 个')

            # 测试限制
            if config.DETAIL_LIMIT:
                products = products[: config.DETAIL_LIMIT]
                print(f'  [测试] 仅爬前 {len(products)} 个详情')

            # 详情页
            for i, p in enumerate(products):
                print(f'  [详情] {i + 1}/{len(products)}: {p["title"][:50]}')
                p = await scraper.scrape_detail(p)
                await asyncio.sleep(config.DETAIL_DELAY)

            all_products.extend(products)
    finally:
        await scraper.close()

    # 去重（同一 product_id 只保留一条；不同规格 = 不同 product_id，自然保留）
    seen = set()
    unique = []
    for p in all_products:
        if p['product_id'] not in seen:
            seen.add(p['product_id'])
            unique.append(p)

    export(unique, config.OUTPUT_DIR, config.CSV_NAME)
    print(f'\n完成！共 {len(unique)} 个商品 → {config.OUTPUT_DIR}/')
    return unique


if __name__ == '__main__':
    asyncio.run(run())
