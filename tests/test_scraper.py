#!/usr/bin/env python3
"""
Unit tests for Donizo Material Scraper
"""

import unittest
import asyncio
import json
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import sys

# Add parent directory to path to import scraper
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import MaterialScraper, Product


class TestProduct(unittest.TestCase):
    """Test Product dataclass"""
    
    def test_product_creation(self):
        """Test creating a product with required fields"""
        product = Product(
            name="Carrelage Test",
            category="carrelage",
            price=29.99,
            currency="EUR",
            product_url="https://example.com/product/1",
            supplier="Test Supplier"
        )
        
        self.assertEqual(product.name, "Carrelage Test")
        self.assertEqual(product.category, "carrelage")
        self.assertEqual(product.price, 29.99)
        self.assertEqual(product.currency, "EUR")
        self.assertTrue(product.in_stock)
        self.assertIsNotNone(product.scraped_at)
    
    def test_product_with_optional_fields(self):
        """Test creating a product with all fields"""
        product = Product(
            name="Lavabo Premium",
            category="lavabos",
            price=159.99,
            currency="EUR",
            product_url="https://example.com/product/2",
            brand="Brand Test",
            unit="pièce",
            pack_size="1",
            image_url="https://example.com/image.jpg",
            in_stock=False,
            supplier="Test Supplier"
        )
        
        self.assertEqual(product.brand, "Brand Test")
        self.assertEqual(product.unit, "pièce")
        self.assertFalse(product.in_stock)


class TestMaterialScraper(unittest.TestCase):
    """Test MaterialScraper class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "test_config.yaml")
        
        # Create a test config file
        test_config = """
suppliers:
  leroymerlin:
    base_url: "https://www.leroymerlin.fr"
    categories:
      test_category: "/test-path"

scraping:
  delay_min: 0.1
  delay_max: 0.2
  max_products_per_category: 5
  max_concurrent_requests: 1
"""
        with open(self.config_path, 'w') as f:
            f.write(test_config)
    
    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_load_config(self):
        """Test configuration loading"""
        scraper = MaterialScraper(self.config_path)
        
        self.assertIn('suppliers', scraper.config)
        self.assertIn('leroymerlin', scraper.config['suppliers'])
        self.assertEqual(
            scraper.config['scraping']['max_products_per_category'], 
            5
        )
    
    def test_load_config_fallback(self):
        """Test fallback to default config when file not found"""
        scraper = MaterialScraper("non_existent_config.yaml")
        
        self.assertIn('suppliers', scraper.config)
        self.assertIn('scraping', scraper.config)
    
    def test_parse_price(self):
        """Test price parsing functionality"""
        scraper = MaterialScraper(self.config_path)
        
        # Test various price formats
        test_cases = [
            ("29,99 €", (29.99, "EUR")),
            ("159.50€", (159.50, "EUR")),
            ("1 299,00 EUR", (1299.00, "EUR")),
            ("invalid", (0.0, "EUR")),
            ("", (0.0, "EUR")),
        ]
        
        for price_text, expected in test_cases:
            with self.subTest(price_text=price_text):
                result = scraper._parse_price(price_text)
                self.assertEqual(result, expected)
    
    def test_extract_unit(self):
        """Test unit extraction from text"""
        scraper = MaterialScraper(self.config_path)
        
        test_cases = [
            ("Carrelage 60x60 cm - lot de 5 pièces", "pièce"),
            ("Peinture 2,5L blanc", "l"),
            ("Lavabo en céramique - 1 kg", "kg"),
            ("Simple product name", None),
        ]
        
        for text, expected in test_cases:
            with self.subTest(text=text):
                result = scraper._extract_unit(text)
                if expected:
                    self.assertEqual(result.lower(), expected.lower())
                else:
                    self.assertIsNone(result)


class TestScrapingFunctions(unittest.IsolatedAsyncioTestCase):
    """Test async scraping functions"""
    
    async def asyncSetUp(self):
        """Async setup"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "test_config.yaml")
        
        test_config = """
suppliers:
  leroymerlin:
    base_url: "https://www.leroymerlin.fr"
    categories:
      test_category: "/test-path"

scraping:
  delay_min: 0
  delay_max: 0
  max_products_per_category: 5
  max_concurrent_requests: 1
"""
        with open(self.config_path, 'w') as f:
            f.write(test_config)
    
    async def asyncTearDown(self):
        """Async cleanup"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    @patch('aiohttp.ClientSession.get')
    async def test_fetch_page_success(self, mock_get):
        """Test successful page fetching"""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="<html>Test content</html>")
        mock_get.return_value.__aenter__.return_value = mock_response
        
        async with MaterialScraper(self.config_path) as scraper:
            products = await scraper._scrape_leroymerlin_category("test_category", "/test-path")
            
            self.assertEqual(len(products), 2)
            self.assertEqual(products[0].name, "Product 1")
            self.assertEqual(products[1].name, "Product 2")
    
    async def test_save_data(self):
        """Test saving data to JSON file"""
        async with MaterialScraper(self.config_path) as scraper:
            # Add test products
            scraper.products = [
                Product(
                    name="Test Product 1",
                    category="test_category",
                    price=99.99,
                    currency="EUR",
                    product_url="https://test.com/1",
                    supplier="Test Supplier"
                ),
                Product(
                    name="Test Product 2",
                    category="test_category",
                    price=199.99,
                    currency="EUR",
                    product_url="https://test.com/2",
                    supplier="Test Supplier"
                )
            ]
            
            # Save to temp file
            output_file = os.path.join(self.temp_dir, "test_output.json")
            scraper.save_data(output_file)
            
            # Verify file was created and contains correct data
            self.assertTrue(os.path.exists(output_file))
            
            with open(output_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.assertEqual(data['total_products'], 2)
            self.assertEqual(len(data['products']), 2)
            self.assertEqual(data['products'][0]['name'], "Test Product 1")
    
    async def test_get_summary(self):
        """Test summary statistics generation"""
        async with MaterialScraper(self.config_path) as scraper:
            # Add test products
            scraper.products = [
                Product(name="P1", category="cat1", price=10.0, currency="EUR", product_url="url1", supplier="S1"),
                Product(name="P2", category="cat1", price=20.0, currency="EUR", product_url="url2", supplier="S1"),
                Product(name="P3", category="cat2", price=30.0, currency="EUR", product_url="url3", supplier="S2"),
            ]
            
            summary = scraper.get_summary()
            
            self.assertEqual(summary['total_products'], 3)
            self.assertEqual(summary['categories']['cat1'], 2)
            self.assertEqual(summary['categories']['cat2'], 1)
            self.assertEqual(summary['suppliers']['S1'], 2)
            self.assertEqual(summary['suppliers']['S2'], 1)
            self.assertEqual(summary['average_price'], 20.0)
            self.assertEqual(summary['price_range']['min'], 10.0)
            self.assertEqual(summary['price_range']['max'], 30.0)


class TestIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests"""
    
    async def asyncSetUp(self):
        """Setup for integration tests"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "integration_config.yaml")
        
        # Create integration test config
        test_config = """
suppliers:
  leroymerlin:
    base_url: "https://httpbin.org"  # Use httpbin for testing
    categories:
      test: "/html"

scraping:
  delay_min: 0
  delay_max: 0
  max_products_per_category: 1
  max_concurrent_requests: 1
"""
        with open(self.config_path, 'w') as f:
            f.write(test_config)
    
    async def asyncTearDown(self):
        """Cleanup integration tests"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    async def test_full_scraping_workflow(self):
        """Test the complete scraping workflow with mocked data"""
        with patch('scraper.MaterialScraper._fetch_page') as mock_fetch:
            # Mock HTML response
            mock_fetch.return_value = """
            <html>
                <div data-product-id="test1">
                    <h2>Test Product</h2>
                    <span class="price">29,99 €</span>
                    <img src="/test.jpg" alt="test">
                </div>
            </html>
            """
            
            async with MaterialScraper(self.config_path) as scraper:
                products = await scraper.scrape_all()
                
                # Should have attempted to scrape
                self.assertIsInstance(products, list)
                
                # Test saving
                output_file = os.path.join(self.temp_dir, "integration_test.json")
                scraper.save_data(output_file)
                
                self.assertTrue(os.path.exists(output_file))


class TestErrorHandling(unittest.TestCase):
    """Test error handling scenarios"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "error_test_config.yaml")
        
        # Create minimal config
        test_config = """
suppliers:
  leroymerlin:
    base_url: "https://www.leroymerlin.fr"
    categories:
      test: "/test"
scraping:
  delay_min: 0
  delay_max: 0
  max_products_per_category: 1
  max_concurrent_requests: 1
"""
        with open(self.config_path, 'w') as f:
            f.write(test_config)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_invalid_price_parsing(self):
        """Test handling of invalid price formats"""
        scraper = MaterialScraper(self.config_path)
        
        invalid_prices = [
            "abc",
            "€€€",
            "",
            None,
            "prix sur demande",
        ]
        
        for invalid_price in invalid_prices:
            with self.subTest(price=invalid_price):
                price, currency = scraper._parse_price(str(invalid_price) if invalid_price else "")
                self.assertEqual(price, 0.0)
                self.assertEqual(currency, "EUR")
    
    def test_malformed_html_handling(self):
        """Test parsing with malformed HTML"""
        scraper = MaterialScraper(self.config_path)
        
        # This should not crash the scraper
        from bs4 import BeautifulSoup
        malformed_html = "<div><span>Incomplete tag"
        soup = BeautifulSoup(malformed_html, 'html.parser')
        
        # Should handle gracefully
        result = asyncio.run(scraper._parse_leroymerlin_product(
            soup, "test_category", "https://test.com"
        ))
        
        # Should return None for unparseable content
        self.assertIsNone(result)


if __name__ == '__main__':
    # Create test suite
    test_classes = [
        TestProduct,
        TestMaterialScraper, 
        TestScrapingFunctions,
        TestIntegration,
        TestErrorHandling
    ]
    
    suite = unittest.TestSuite()
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Exit with error code if tests failed
    exit(0 if result.wasSuccessful() else 1)
            result = await scraper._fetch_page("https://test.com")
            self.assertEqual(result, "<html>Test content</html>")
    
    @patch('aiohttp.ClientSession.get')
    async def test_fetch_page_failure(self, mock_get):
        """Test failed page fetching"""
        # Mock failed response
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_get.return_value.__aenter__.return_value = mock_response
        
        async with MaterialScraper(self.config_path) as scraper:
            result = await scraper._fetch_page("https://test.com")
            self.assertIsNone(result)
    
    @patch('scraper.MaterialScraper._fetch_page')
    @patch('scraper.MaterialScraper._parse_leroymerlin_product')
    async def test_scrape_leroymerlin_category(self, mock_parse_product, mock_fetch_page):
        """Test scraping a Leroy Merlin category"""
        # Mock HTML content with product containers
        mock_html = """
        <html>
            <div data-product-id="1">Product 1</div>
            <div data-product-id="2">Product 2</div>
        </html>
        """
        mock_fetch_page.return_value = mock_html
        
        # Mock parsed products
        mock_product1 = Product(
            name="Product 1",
            category="test_category",
            price=10.0,
            currency="EUR",
            product_url="https://test.com/1",
            supplier="Leroy Merlin"
        )
        mock_product2 = Product(
            name="Product 2",
            category="test_category",
            price=20.0,
            currency="EUR",
            product_url="https://test.com/2",
            supplier="Leroy Merlin"
        )
        
        mock_parse_product.side_effect = [mock_product1, mock_product2]
        
        async with MaterialScraper(self.config_path) as scraper: