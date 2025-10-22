import requests
import sys
import json
from datetime import datetime

class VideoDownloaderAPITester:
    def __init__(self, base_url="https://upvideo.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED")
        else:
            print(f"❌ {name} - FAILED: {details}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })

    def test_api_root(self):
        """Test API root endpoint"""
        try:
            response = requests.get(f"{self.api_url}/", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}, Response: {response.text[:100]}"
            self.log_test("API Root Endpoint", success, details)
            return success
        except Exception as e:
            self.log_test("API Root Endpoint", False, str(e))
            return False

    def test_status_endpoints(self):
        """Test status check endpoints"""
        try:
            # Test POST /status
            test_data = {"client_name": "test_client"}
            response = requests.post(f"{self.api_url}/status", json=test_data, timeout=10)
            post_success = response.status_code == 200
            
            if post_success:
                status_id = response.json().get('id')
                self.log_test("POST /status", True, f"Created status with ID: {status_id}")
            else:
                self.log_test("POST /status", False, f"Status: {response.status_code}")
            
            # Test GET /status
            response = requests.get(f"{self.api_url}/status", timeout=10)
            get_success = response.status_code == 200
            
            if get_success:
                statuses = response.json()
                self.log_test("GET /status", True, f"Retrieved {len(statuses)} status records")
            else:
                self.log_test("GET /status", False, f"Status: {response.status_code}")
            
            return post_success and get_success
        except Exception as e:
            self.log_test("Status Endpoints", False, str(e))
            return False

    def test_analyze_video(self, test_url="https://www.youtube.com/watch?v=jNQXAC9IVRw"):
        """Test video analysis endpoint"""
        try:
            print(f"\n🔍 Testing video analysis with URL: {test_url}")
            
            response = requests.post(
                f"{self.api_url}/analyze",
                json={"url": test_url},
                timeout=30  # Video analysis can take time
            )
            
            success = response.status_code == 200
            
            if success:
                data = response.json()
                required_fields = ['title', 'source', 'formats']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    self.log_test("Video Analysis", False, f"Missing fields: {missing_fields}")
                    return False
                
                formats_count = len(data.get('formats', []))
                details = f"Title: {data['title'][:50]}..., Source: {data['source']}, Formats: {formats_count}"
                self.log_test("Video Analysis", True, details)
                
                # Store video info for download test
                self.video_info = data
                return True
            else:
                error_detail = response.text
                self.log_test("Video Analysis", False, f"Status: {response.status_code}, Error: {error_detail}")
                return False
                
        except Exception as e:
            self.log_test("Video Analysis", False, str(e))
            return False

    def test_download_video(self):
        """Test video download endpoint (without actually downloading full file)"""
        if not hasattr(self, 'video_info') or not self.video_info:
            self.log_test("Video Download", False, "No video info available from analysis")
            return False
        
        try:
            formats = self.video_info.get('formats', [])
            if not formats:
                self.log_test("Video Download", False, "No formats available")
                return False
            
            # Use the first available format
            format_id = formats[0]['format_id']
            test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
            
            print(f"\n⬇️ Testing download with format: {format_id}")
            
            # Make request but don't download full file - just check if it starts
            response = requests.post(
                f"{self.api_url}/download",
                json={"url": test_url, "format_id": format_id},
                timeout=15,
                stream=True  # Stream to avoid downloading full file
            )
            
            success = response.status_code == 200
            
            if success:
                # Check if response has video content type
                content_type = response.headers.get('content-type', '')
                content_disposition = response.headers.get('content-disposition', '')
                
                if 'video' in content_type or 'attachment' in content_disposition:
                    self.log_test("Video Download", True, f"Download started successfully, Content-Type: {content_type}")
                    return True
                else:
                    self.log_test("Video Download", False, f"Unexpected content type: {content_type}")
                    return False
            else:
                error_detail = response.text[:200]
                self.log_test("Video Download", False, f"Status: {response.status_code}, Error: {error_detail}")
                return False
                
        except Exception as e:
            self.log_test("Video Download", False, str(e))
            return False

    def test_invalid_url_handling(self):
        """Test how API handles invalid URLs"""
        try:
            invalid_urls = [
                "not_a_url",
                "https://invalid-domain-that-does-not-exist.com/video",
                "https://www.youtube.com/watch?v=invalid_video_id_12345"
            ]
            
            all_handled_correctly = True
            
            for invalid_url in invalid_urls:
                response = requests.post(
                    f"{self.api_url}/analyze",
                    json={"url": invalid_url},
                    timeout=15
                )
                
                # Should return 400 or similar error status
                if response.status_code >= 400:
                    print(f"✅ Invalid URL '{invalid_url[:30]}...' correctly rejected with status {response.status_code}")
                else:
                    print(f"❌ Invalid URL '{invalid_url[:30]}...' was not rejected (status: {response.status_code})")
                    all_handled_correctly = False
            
            self.log_test("Invalid URL Handling", all_handled_correctly, 
                         "Tested multiple invalid URLs" if all_handled_correctly else "Some invalid URLs were not properly rejected")
            return all_handled_correctly
            
        except Exception as e:
            self.log_test("Invalid URL Handling", False, str(e))
            return False

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting Video Downloader API Tests")
        print(f"📍 Testing against: {self.base_url}")
        print("=" * 60)
        
        # Test basic connectivity
        if not self.test_api_root():
            print("❌ API root endpoint failed - stopping tests")
            return False
        
        # Test status endpoints
        self.test_status_endpoints()
        
        # Test video analysis
        analysis_success = self.test_analyze_video()
        
        # Test download only if analysis succeeded
        if analysis_success:
            self.test_download_video()
        
        # Test error handling
        self.test_invalid_url_handling()
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} tests passed")
        print(f"✅ Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return True
        else:
            print("⚠️  Some tests failed - check details above")
            return False

def main():
    tester = VideoDownloaderAPITester()
    success = tester.run_all_tests()
    
    # Save detailed results
    with open('/app/backend_test_results.json', 'w') as f:
        json.dump({
            'summary': {
                'total_tests': tester.tests_run,
                'passed_tests': tester.tests_passed,
                'success_rate': (tester.tests_passed/tester.tests_run)*100 if tester.tests_run > 0 else 0,
                'timestamp': datetime.now().isoformat()
            },
            'detailed_results': tester.test_results
        }, f, indent=2)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())