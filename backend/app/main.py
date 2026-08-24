"""
Main FastAPI application for Reclaim
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import engine, Base
from app.api import (
    mandates_router, recovery_router, classification_router, 
    compliance_router, dashboard_router
)

# Create FastAPI app
app = FastAPI(
    title="Reclaim API",
    description="UPI AutoPay Mandate Recovery Engine",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(mandates_router)
app.include_router(recovery_router)
app.include_router(classification_router)
app.include_router(compliance_router)
app.include_router(dashboard_router)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    # Create tables
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Reclaim: UPI AutoPay Mandate Recovery Engine",
        "version": "0.1.0",
        "status": "operational"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
