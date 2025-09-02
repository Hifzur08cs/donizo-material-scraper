#!/usr/bin/env python3
"""
Donizo Material Scraper API Server
Simulates API endpoints for scraped material data (Bonus Feature)
"""

from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path as PathLib
import uvicorn
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for API responses
class ProductResponse(BaseModel):
    name: str
    category: str
    price: float
    currency: str = "EUR"
    product_url: str
    brand: Optional[str] = None
    unit: Optional[str] = None
    pack_size: Optional[str] = None
    image_url: Optional[str] = None
    in_stock: bool = True
    supplier: str
    scraped_at: str

class MaterialsResponse(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int
    products: List[ProductResponse]
    filters_applied: Dict[str, Any]

class CategoryResponse(BaseModel):
    name: str
    product_count: int
    average_price: float
    price_range: Dict[str, float]
    suppliers: List[str]

class SupplierResponse(BaseModel):
    name: str
    product_count: int
    categories: List[str]
    average_price: float
    last_updated: str

class StatsResponse(BaseModel):
    total_products: int
    total_suppliers: int
    total_categories: int
    average_price: float
    price_range: Dict[str, float]
    last_updated: str

class DonizoAPI:
    """API class for serving scraped material data"""
    
    def __init__(self, data_file: str = "data/materials.json"):
        self.data_file = data_file
        self.app = FastAPI(
            title="Donizo Material Pricing API",
            description="API for renovation material pricing data scraped from French suppliers",
            version="1.0.0",
            docs_url="/docs",
            redoc_url="/redoc"
        )
        self.data = self._load_data()
        self._setup_middleware()
        self._setup_routes()
    
    def _load_data(self) -> Dict[str, Any]:
        """Load scraped data from JSON file"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"Loaded {data.get('total_products', 0)} products from {self.data_file}")
                return data
        except FileNotFoundError:
            logger.warning(f"Data file {self.data_file} not found, using empty dataset")
            return {"products": [], "total_products": 0, "scraped_at": datetime.now().isoformat()}
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON data: {e}")
            return {"products": [], "total_products": 0, "scraped_at": datetime.now().isoformat()}
    
    def _setup_middleware(self):
        """Setup CORS middleware"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Configure appropriately for production
            allow_credentials=True,
            allow_methods=["GET"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.app.get("/", response_class=JSONResponse)
        async def root():
            """API root endpoint"""
            return {
                "message": "Donizo Material Pricing API",
                "version": "1.0.0",
                "total_products": self.data.get("total_products", 0),
                "last_updated": self.data.get("scraped_at", ""),
                "endpoints": {
                    "materials": "/materials",
                    "categories": "/categories",
                    "suppliers": "/suppliers",
                    "stats": "/stats",
                    "docs": "/docs"
                }
            }
        
        @self.app.get("/materials", response_model=MaterialsResponse)
        async def get_materials(
            page: int = Query(1, ge=1, description="Page number"),
            per_page: int = Query(20, ge=1, le=100, description="Items per page"),
            category: Optional[str] = Query(None, description="Filter by category"),
            supplier: Optional[str] = Query(None, description="Filter by supplier"),
            min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
            max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
            brand: Optional[str] = Query(None, description="Filter by brand"),
            in_stock: Optional[bool] = Query(None, description="Filter by stock status"),
            search: Optional[str] = Query(None, description="Search in product names")
        ):
            """Get materials with filtering and pagination"""
            products = self.data.get("products", [])
            
            # Apply filters
            filters_applied = {}
            
            if category:
                products = [p for p in products if p.get("category", "").lower() == category.lower()]
                filters_applied["category"] = category
            
            if supplier:
                products = [p for p in products if supplier.lower() in p.get("supplier", "").lower()]
                filters_applied["supplier"] = supplier
            
            if min_price is not None:
                products = [p for p in products if p.get("price", 0) >= min_price]
                filters_applied["min_price"] = min_price
            
            if max_price is not None:
                products = [p for p in products if p.get("price", 0) <= max_price]
                filters_applied["max_price"] = max_price
            
            if brand:
                products = [p for p in products if brand.lower() in (p.get("brand") or "").lower()]
                filters_applied["brand"] = brand
            
            if in_stock is not None:
                products = [p for p in products if p.get("in_stock", True) == in_stock]
                filters_applied["in_stock"] = in_stock
            
            if search:
                search_lower = search.lower()
                products = [p for p in products if search_lower in p.get("name", "").lower()]
                filters_applied["search"] = search
            
            # Pagination
            total = len(products)
            total_pages = (total + per_page - 1) // per_page
            start = (page - 1) * per_page
            end = start + per_page
            paginated_products = products[start:end]
            
            return MaterialsResponse(
                total=total,
                page=page,
                per_page=per_page,
                total_pages=total_pages,
                products=[ProductResponse(**p) for p in paginated_products],
                filters_applied=filters_applied
            )
        
        @self.app.get("/materials/{category}", response_model=MaterialsResponse)
        async def get_materials_by_category(
            category: str = Path(..., description="Category name"),
            page: int = Query(1, ge=1),
            per_page: int = Query(20, ge=1, le=100)
        ):
            """Get materials by specific category"""
            return await get_materials(page=page, per_page=per_page, category=category)
        
        @self.app.get("/categories", response_model=List[CategoryResponse])
        async def get_categories():
            """Get all categories with statistics"""
            products = self.data.get("products", [])
            categories = {}
            
            for product in products:
                cat = product.get("category", "unknown")
                if cat not in categories:
                    categories[cat] = {
                        "products": [],
                        "suppliers": set()
                    }
                categories[cat]["products"].append(product)
                categories[cat]["suppliers"].add(product.get("supplier", "unknown"))
            
            result = []
            for cat_name, cat_data in categories.items():
                prices = [p.get("price", 0) for p in cat_data["products"] if p.get("price", 0) > 0]
                
                result.append(CategoryResponse(
                    name=cat_name,
                    product_count=len(cat_data["products"]),
                    average_price=sum(prices) / len(prices) if prices else 0,
                    price_range={
                        "min": min(prices) if prices else 0,
                        "max": max(prices) if prices else 0
                    },
                    suppliers=list(cat_data["suppliers"])
                ))
            
            return sorted(result, key=lambda x: x.product_count, reverse=True)
        
        @self.app.get("/suppliers", response_model=List[SupplierResponse])
        async def get_suppliers():
            """Get all suppliers with statistics"""
            products = self.data.get("products", [])
            suppliers = {}
            
            for product in products:
                sup = product.get("supplier", "unknown")
                if sup not in suppliers:
                    suppliers[sup] = {
                        "products": [],
                        "categories": set()
                    }
                suppliers[sup]["products"].append(product)
                suppliers[sup]["categories"].add(product.get("category", "unknown"))
            
            result = []
            for sup_name, sup_data in suppliers.items():
                prices = [p.get("price", 0) for p in sup_data["products"] if p.get("price", 0) > 0]
                
                result.append(SupplierResponse(
                    name=sup_name,
                    product_count=len(sup_data["products"]),
                    categories=list(sup_data["categories"]),
                    average_price=sum(prices) / len(prices) if prices else 0,
                    last_updated=self.data.get("scraped_at", "")
                ))
            
            return sorted(result, key=lambda x: x.product_count, reverse=True)
        
        @self.app.get("/stats", response_model=StatsResponse)
        async def get_stats():
            """Get overall statistics"""
            products = self.data.get("products", [])
            
            if not products:
                return StatsResponse(
                    total_products=0,
                    total_suppliers=0,
                    total_categories=0,
                    average_price=0,
                    price_range={"min": 0, "max": 0},
                    last_updated=self.data.get("scraped_at", "")
                )
            
            prices = [p.get("price", 0) for p in products if p.get("price", 0) > 0]
            suppliers = set(p.get("supplier", "unknown") for p in products)
            categories = set(p.get("category", "unknown") for p in products)
            
            return StatsResponse(
                total_products=len(products),
                total_suppliers=len(suppliers),
                total_categories=len(categories),
                average_price=sum(prices) / len(prices) if prices else 0,
                price_range={
                    "min": min(prices) if prices else 0,
                    "max": max(prices) if prices else 0
                },
                last_updated=self.data.get("scraped_at", "")
            )
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "data_file": self.data_file,
                "products_loaded": self.data.get("total_products", 0)
            }
        
        @self.app.post("/refresh")
        async def refresh_data():
            """Refresh data from file"""
            self.data = self._load_data()
            return {
                "status": "refreshed",
                "products_loaded": self.data.get("total_products", 0),
                "timestamp": datetime.now().isoformat()
            }

def create_app(data_file: str = "data/materials.json") -> FastAPI:
    """Factory function to create FastAPI app"""
    donizo_api = DonizoAPI(data_file)
    return donizo_api.app

def main():
    """Main function to run the API server"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Donizo Material Pricing API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--data-file", default="data/materials.json", help="Path to data file")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    args = parser.parse_args()
    
    # Check if data file exists
    if not PathLib(args.data_file).exists():
        logger.warning(f"Data file {args.data_file} not found. API will serve empty dataset.")
        logger.info("Run the scraper first: python scraper.py")
    
    # Create and run the app
    app = create_app(args.data_file)
    
    logger.info(f"Starting Donizo API server on {args.host}:{args.port}")
    logger.info(f"API docs available at: http://{args.host}:{args.port}/docs")
    
    uvicorn.run(
        "api_server:create_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
        app_dir=".",
        log_level="info"
    )

if __name__ == "__main__":
    main()