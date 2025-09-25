import requests
import pprint

BASE_URL = "http://91.98.200.67"

def test_health_check():
    print("Testing health check endpoint...")
    resp = requests.get(f"{BASE_URL}/")
    assert resp.status_code == 200, f"Status code: {resp.status_code}"
    data = resp.json()
    print("Health check response:", data)
    assert data.get("status") == "healthy"
    assert "service" in data

def test_list_available_ids():
    print("Testing available IDs endpoint...")
    resp = requests.get(f"{BASE_URL}/api/available-ids")
    assert resp.status_code == 200, f"Status code: {resp.status_code}"
    data = resp.json()
    print("Available IDs response:")
    pprint.pprint(data)
    assert "available_ids" in data
    assert isinstance(data["available_ids"], list)
    assert data["count"] == len(data["available_ids"])
    if data["available_ids"]:
        return data["available_ids"][0]["id"]
    return None

def test_get_energy_data(file_id, days_back=1):
    print(f"Testing energy data endpoint for id={file_id}, days_back={days_back}...")
    params = {
        "id": file_id,
        "days_back": days_back
    }
    resp = requests.get(f"{BASE_URL}/api/energy-data", params=params)
    assert resp.status_code == 200, f"Status code: {resp.status_code}"
    data = resp.json()
    print("Energy data response keys:", list(data.keys()))
    assert data.get("id") == file_id
    assert "data" in data
    assert isinstance(data["data"], list)
    assert len(data["data"]) == 24, f"Expected 24 hourly datapoints, got {len(data['data'])}"
    print("Sample data point:")
    pprint.pprint(data["data"][0])
    assert "timestamp" in data["data"][0]
    assert "net_load" in data["data"][0]
    assert "SOC_opt" in data["data"][0]
    assert "metadata" in data
    print("Metadata:")
    pprint.pprint(data["metadata"])

if __name__ == "__main__":
    test_health_check()
    file_id = test_list_available_ids()
    if file_id:
        test_get_energy_data(file_id)
    else:
        print("No available file IDs found.")
