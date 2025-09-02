#!/usr/bin/env python3
"""
Donizo Material Scraper - Main Scraping Engine
Scrapes renovation material pricing data from French suppliers
"""

import asyncio
import aiohttp
import json
import yaml
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import random
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class Product:
    """Data structure for a scraped product"""
    name: str
    category: str
    price: float
    currency: str
    product_url: str
    brand: Optional[str] = None
    unit: Optional[str] = None
    pack_size: Optional[str] = None
    image_url: Optional[str] = None
    in_stock: bool = True
    supplier: str = ""
    scraped_at: str = ""
    
    def __post_init__(self):
        if not self.scraped_at:
            self.scraped_at = datetime.now().isoformat()

class MaterialScraper:
    """Main scraper class for renovation materials"""
    
    def __init__(self, config_path: str = "config/scraper_config.yaml"):
        self.config = self._load_config(config_path)
        self.session: Optional[aiohttp.ClientSession] = None
        self.products: List[Product] = []
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {config_path} not found, using defaults")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Default configuration if file not found"""
        return {
            'suppliers': {
                'leroymerlin': {
                    'base_url': 'https://www.leroymerlin.fr',
                    'categories': {
                        'carrelage': '/carrelage-parquet/carrelage-sol-mur',
                        'lavabos': '/salle-de-bains/lavabo-vasque',
                        'wc': '/salle-de-bains/wc-toilettes',
                        'peinture': '/peinture-droguerie/peinture-interieur',
                        'meuble-vasque': '/salle-de-bains/meuble-de-salle-de-bains',
                        'douche': '/salle-de-bains/douche'
                    }
                }
            },
            'scraping': {
                'delay_min': 1,
                'delay_max': 3,
                'max_products_per_category': 50,
                'max_concurrent_requests': 3
            }
        }
    
    async def __aenter__(self):
        """Async context manager entry"""
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=3)
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            headers=self.headers,
            connector=connector,
            timeout=timeout
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch a single page with error handling and rate limiting"""
        try:
            await asyncio.sleep(random.uniform(
                self.config['scraping']['delay_min'],
                self.config['scraping']['delay_max']
            ))
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    content = await response.text()
                    logger.info(f"Successfully fetched: {url}")
                    return content
                else:
                    logger.warning(f"HTTP {response.status} for {url}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return None
    
    def _parse_price(self, price_text: str) -> tuple[float, str]:
        """Parse price text and return (price, currency)"""
        if not price_text:
            return 0.0, "EUR"
        
        # Remove whitespace and common price indicators
        price_clean = re.sub(r'[^\d,.]', '', price_text.replace(',', '.'))
        
        try:
            price = float(price_clean)
            currency = "EUR" if "€" in price_text else "EUR"  # Default to EUR for French sites
            return price, currency
        except ValueError:
            logger.warning(f"Could not parse price: {price_text}")
            return 0.0, "EUR"
    
    def _extract_unit(self, text: str) -> Optional[str]:
        """Extract measurement unit from product text"""
        if not text:
            return None
        
        # Common units in French
        units = ['m²', 'm2', 'cm²', 'cm2', 'ml', 'cl', 'l', 'kg', 'g', 'pièce', 'lot', 'paquet']
        text_lower = text.lower()
        
        for unit in units:
            if unit.lower() in text_lower:
                return unit
        
        return None
    
    async def _scrape_leroymerlin_category(self, category: str, category_url: str) -> List[Product]:
        """Scrape products from Leroy Merlin category page"""
        products = []
        base_url = self.config['suppliers']['leroymerlin']['base_url']
        full_url = urljoin(base_url, category_url)
        
        logger.info(f"Scraping Leroy Merlin {category}: {full_url}")
        
        # Handle pagination
        page = 1
        max_products = self.config['scraping']['max_products_per_category']
        
        while len(products) < max_products:
            page_url = f"{full_url}?page={page}"
            content = await self._fetch_page(page_url)
            
            if not content:
                break
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # Find product containers (adjust selectors based on actual HTML structure)
            product_containers = soup.find_all(['div', 'article'], class_=re.compile(r'product|item|card', re.I))
            
            if not product_containers:
                # Try alternative selectors
                product_containers = soup.find_all('div', attrs={'data-product-id': True})
            
            if not product_containers:
                logger.warning(f"No products found on page {page} for {category}")
                break
            
            page_products = 0
            for container in product_containers[:max_products - len(products)]:
                product = await self._parse_leroymerlin_product(container, category, base_url)
                if product:
                    products.append(product)
                    page_products += 1
            
            if page_products == 0:
                break
            
            page += 1
            
            # Safety break for pagination
            if page > 10:
                break
        
        logger.info(f"Scraped {len(products)} products from {category}")
        return products
    
    async def _parse_leroymerlin_product(self, container, category: str, base_url: str) -> Optional[Product]:
        """Parse individual product from Leroy Merlin"""
        try:
            # Product name
            name_elem = container.find(['h2', 'h3', 'a'], class_=re.compile(r'title|name|product', re.I))
            if not name_elem:
                name_elem = container.find('a', title=True)
            
            if not name_elem:
                return None
            
            name = name_elem.get_text(strip=True) or name_elem.get('title', '')
            
            # Product URL
            url_elem = container.find('a', href=True)
            if not url_elem:
                return None
            
            product_url = urljoin(base_url, url_elem['href'])
            
            # Price
            price_elem = container.find(['span', 'div'], class_=re.compile(r'price|prix', re.I))
            if not price_elem:
                price_elem = container.find(string=re.compile(r'€|\d+[,.]?\d*'))
                if price_elem:
                    price_elem = price_elem.parent
            
            price, currency = self._parse_price(price_elem.get_text() if price_elem else "0")
            
            # Brand
            brand_elem = container.find(['span', 'div'], class_=re.compile(r'brand|marque', re.I))
            brand = brand_elem.get_text(strip=True) if brand_elem else None
            
            # Image URL
            img_elem = container.find('img')
            image_url = None
            if img_elem:
                image_url = img_elem.get('src') or img_elem.get('data-src')
                if image_url and not image_url.startswith('http'):
                    image_url = urljoin(base_url, image_url)
            
            # Unit and pack size
            unit = self._extract_unit(name)
            
            # Stock status
            stock_elem = container.find(['span', 'div'], class_=re.compile(r'stock|disponib', re.I))
            in_stock = True
            if stock_elem:
                stock_text = stock_elem.get_text().lower()
                in_stock = 'disponible' in stock_text or 'en stock' in stock_text
            
            product = Product(
                name=name,
                category=category,
                price=price,
                currency=currency,
                product_url=product_url,
                brand=brand,
                unit=unit,
                image_url=image_url,
                in_stock=in_stock,
                supplier="Leroy Merlin"
            )
            
            return product
            
        except Exception as e:
            logger.error(f"Error parsing product: {str(e)}")
            return None
    
    async def scrape_supplier(self, supplier_name: str) -> List[Product]:
        """Scrape all categories from a specific supplier"""
        if supplier_name not in self.config['suppliers']:
            logger.error(f"Supplier {supplier_name} not configured")
            return []
        
        supplier_config = self.config['suppliers'][supplier_name]
        categories = supplier_config['categories']
        
        tasks = []
        for category, url in categories.items():
            if supplier_name == 'leroymerlin':
                task = self._scrape_leroymerlin_category(category, url)
            else:
                # Add other suppliers here
                logger.warning(f"Scraper for {supplier_name} not implemented")
                continue
            
            tasks.append(task)
        
        # Execute with concurrency limit
        semaphore = asyncio.Semaphore(self.config['scraping']['max_concurrent_requests'])
        
        async def bounded_task(task):
            async with semaphore:
                return await task
        
        results = await asyncio.gather(*[bounded_task(task) for task in tasks])
        
        # Flatten results
        all_products = []
        for product_list in results:
            all_products.extend(product_list)
        
        return all_products
    
    async def scrape_all(self) -> List[Product]:
        """Scrape all configured suppliers"""
        all_products = []
        
        for supplier_name in self.config['suppliers'].keys():
            logger.info(f"Starting to scrape {supplier_name}")
            products = await self.scrape_supplier(supplier_name)
            all_products.extend(products)
            logger.info(f"Completed {supplier_name}: {len(products)} products")
        
        self.products = all_products
        return all_products
    
    def save_data(self, filepath: str = "data/materials.json"):
        """Save scraped data to JSON file"""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        # Convert products to dictionaries
        data = {
            'scraped_at': datetime.now().isoformat(),
            'total_products': len(self.products),
            'products': [asdict(product) for product in self.products]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(self.products)} products to {filepath}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of scraped data"""
        if not self.products:
            return {}
        
        categories = {}
        suppliers = {}
        total_value = 0
        
        for product in self.products:
            # Count by category
            categories[product.category] = categories.get(product.category, 0) + 1
            
            # Count by supplier
            suppliers[product.supplier] = suppliers.get(product.supplier, 0) + 1
            
            # Sum total value
            total_value += product.price
        
        return {
            'total_products': len(self.products),
            'categories': categories,
            'suppliers': suppliers,
            'average_price': total_value / len(self.products) if self.products else 0,
            'price_range': {
                'min': min(p.price for p in self.products) if self.products else 0,
                'max': max(p.price for p in self.products) if self.products else 0
            }
        }

async def main():
    """Main execution function"""
    logger.info("Starting Donizo Material Scraper")
    
    async with MaterialScraper() as scraper:
        # Scrape all data
        products = await scraper.scrape_all()
        
        # Save data
        scraper.save_data()
        
        # Print summary
        summary = scraper.get_summary()
        logger.info(f"Scraping completed: {summary}")
        
        print(f"\n📊 Scraping Summary:")
        print(f"Total products: {summary.get('total_products', 0)}")
        print(f"Categories: {list(summary.get('categories', {}).keys())}")
        print(f"Suppliers: {list(summary.get('suppliers', {}).keys())}")
        print(f"Average price: €{summary.get('average_price', 0):.2f}")

if __name__ == "__main__":
    asyncio.run(main())