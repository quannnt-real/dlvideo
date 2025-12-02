import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

// Create axios instance
const axiosInstance = axios.create({
  baseURL: BACKEND_URL,
  withCredentials: true, // Send cookies with requests
  timeout: 30000,
});

// Add request interceptor to include session token from localStorage (backup)
axiosInstance.interceptors.request.use(
  (config) => {
    // Get session token from localStorage as backup
    const sessionToken = localStorage.getItem('session_token');
    
    if (sessionToken) {
      config.headers.Authorization = `Bearer ${sessionToken}`;
    }
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add response interceptor to handle 401 errors
axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear session and redirect to login
      localStorage.removeItem('session_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default axiosInstance;
