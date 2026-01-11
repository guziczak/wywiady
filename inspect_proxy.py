
import sys
import os

# Add the tools directory to sys.path
sys.path.insert(0, r"C:\Users\guzic\Documents\GitHub\tools\claude-code-py\src")

try:
    import proxy
    print("Proxy package:", proxy)
    print("Proxy dir:", dir(proxy))
    
    try:
        import proxy.local_proxy
        print("proxy.local_proxy:", proxy.local_proxy)
        print("proxy.local_proxy dir:", dir(proxy.local_proxy))
    except ImportError:
        print("Could not import proxy.local_proxy directly")
    
    # Try to find where start_proxy_server comes from
    from proxy import start_proxy_server
    print("start_proxy_server:", start_proxy_server)
    
except ImportError as e:
    print("ImportError:", e)
except Exception as e:
    print("Error:", e)

