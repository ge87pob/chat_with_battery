#!/usr/bin/env python3
"""
Customer Database Management for Battery Bot
"""

import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

class CustomerDatabase:
    def __init__(self, db_path: str = "customers.db"):
        self.db_path = db_path
        self.init_database()
    
    def clean_text(self, text):
        """Clean text to ensure ASCII compatibility"""
        if text is None:
            return None
        if isinstance(text, str):
            return text.encode('ascii', errors='ignore').decode('ascii')
        return text
    
    def init_database(self):
        """Initialize the customer database with schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create customers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                business_type TEXT,
                building_type TEXT,
                location TEXT,
                address TEXT,
                city TEXT,
                country TEXT,
                latitude REAL,
                longitude REAL,
                capacity_info TEXT,
                special_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create customer_metrics table for tracking usage patterns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customer_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                metric_date DATE,
                avg_daily_consumption REAL,
                peak_load REAL,
                battery_cycles INTEGER,
                savings_eur REAL,
                self_consumption_rate REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # Add default TUM customer if not exists
        self.add_default_customers()
    
    def add_default_customers(self):
        """Add default customers to the database"""
        tum_customer = {
            'data_id': 'klassiche-demo-hackathon-evo-9mflyui8',
            'name': 'TUM Arcisstrasse 80',
            'business_type': 'University',
            'building_type': 'Academic/Research Building',
            'location': 'Munich, Germany',
            'address': 'Arcisstrasse 80, 80333 Munich',
            'city': 'Munich',
            'country': 'Germany',
            'latitude': 48.1374,
            'longitude': 11.5755,
            'capacity_info': '2000 students, mechanical engineering department with heavy machinery',
            'special_notes': 'High energy consumption during academic hours, variable load patterns due to laboratory equipment'
        }
        
        # Only add if doesn't exist
        if not self.get_customer_by_data_id(tum_customer['data_id']):
            self.add_customer(**tum_customer)
    
    def add_customer(self, data_id: str, name: str, business_type: str = None, 
                    building_type: str = None, location: str = None, address: str = None,
                    city: str = None, country: str = None, latitude: float = None, 
                    longitude: float = None, capacity_info: str = None, 
                    special_notes: str = None) -> int:
        """Add a new customer to the database"""
        # Clean all text inputs
        data_id = self.clean_text(data_id)
        name = self.clean_text(name)
        business_type = self.clean_text(business_type)
        building_type = self.clean_text(building_type)
        location = self.clean_text(location)
        address = self.clean_text(address)
        city = self.clean_text(city)
        country = self.clean_text(country)
        capacity_info = self.clean_text(capacity_info)
        special_notes = self.clean_text(special_notes)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO customers 
            (data_id, name, business_type, building_type, location, address, 
             city, country, latitude, longitude, capacity_info, special_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data_id, name, business_type, building_type, location, address,
              city, country, latitude, longitude, capacity_info, special_notes))
        
        customer_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return customer_id
    
    def get_customer_by_data_id(self, data_id: str) -> Optional[Dict]:
        """Get customer information by data_id"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM customers WHERE data_id = ?', (data_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_all_customers(self) -> List[Dict]:
        """Get all customers"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM customers ORDER BY name')
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_customer(self, data_id: str, **updates) -> bool:
        """Update customer information"""
        if not updates:
            return False
        
        # Clean all text updates
        cleaned_updates = {}
        for key, value in updates.items():
            if isinstance(value, str):
                cleaned_updates[key] = self.clean_text(value)
            else:
                cleaned_updates[key] = value
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Build update query dynamically
        set_clauses = []
        values = []
        for key, value in cleaned_updates.items():
            if key != 'data_id':  # Don't allow updating the key
                set_clauses.append(f"{key} = ?")
                values.append(value)
        
        if not set_clauses:
            conn.close()
            return False
        
        values.append(datetime.now())  # updated_at
        values.append(data_id)
        
        query = f'''
            UPDATE customers 
            SET {", ".join(set_clauses)}, updated_at = ?
            WHERE data_id = ?
        '''
        
        cursor.execute(query, values)
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    def get_customer_context(self, data_id: str) -> str:
        """Get formatted customer context for AI prompts"""
        customer = self.get_customer_by_data_id(data_id)
        if not customer:
            return f"Unknown customer (ID: {data_id})"
        
        context_parts = [f"Customer: {customer['name'] or 'Unknown'}"]
        
        if customer['business_type']:
            context_parts.append(f"Business: {customer['business_type']}")
        
        if customer['building_type']:
            context_parts.append(f"Building: {customer['building_type']}")
        
        if customer['location']:
            context_parts.append(f"Location: {customer['location']}")
        
        if customer['capacity_info']:
            context_parts.append(f"Details: {customer['capacity_info']}")
        
        if customer['special_notes']:
            context_parts.append(f"Notes: {customer['special_notes']}")
        
        # Clean the result to ensure ASCII compatibility
        result = " | ".join(context_parts)
        return result.encode('ascii', errors='ignore').decode('ascii')
    
    def log_customer_metrics(self, data_id: str, metric_date: str, 
                           avg_daily_consumption: float = None, peak_load: float = None,
                           battery_cycles: int = None, savings_eur: float = None,
                           self_consumption_rate: float = None):
        """Log daily metrics for a customer"""
        customer = self.get_customer_by_data_id(data_id)
        if not customer:
            return False
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Insert or update metrics for the date
        cursor.execute('''
            INSERT OR REPLACE INTO customer_metrics 
            (customer_id, metric_date, avg_daily_consumption, peak_load, 
             battery_cycles, savings_eur, self_consumption_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (customer['id'], metric_date, avg_daily_consumption, peak_load,
              battery_cycles, savings_eur, self_consumption_rate))
        
        conn.commit()
        conn.close()
        return True
    
    def get_customer_metrics(self, data_id: str, days: int = 30) -> List[Dict]:
        """Get recent metrics for a customer"""
        customer = self.get_customer_by_data_id(data_id)
        if not customer:
            return []
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM customer_metrics 
            WHERE customer_id = ? 
            ORDER BY metric_date DESC 
            LIMIT ?
        ''', (customer['id'], days))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]

if __name__ == "__main__":
    # Test the database
    db = CustomerDatabase()
    
    # Test customer retrieval
    tum = db.get_customer_by_data_id('klassiche-demo-hackathon-evo-9mflyui8')
    print("TUM Customer:", tum['name'] if tum else "Not found")
    
    # Test context generation
    context = db.get_customer_context('klassiche-demo-hackathon-evo-9mflyui8')
    print("Context:", context)
    
    # Test adding another customer
    test_id = db.add_customer(
        data_id='test-customer-123',
        name='Green Office Building',
        business_type='Commercial Office',
        building_type='Office Complex',
        location='Berlin, Germany',
        capacity_info='50 employees, standard office equipment'
    )
    print(f"Added test customer with ID: {test_id}")
    
    # List all customers
    customers = db.get_all_customers()
    print(f"Total customers: {len(customers)}")
    for c in customers:
        print(f"  - {c['name']} ({c['data_id']})")
