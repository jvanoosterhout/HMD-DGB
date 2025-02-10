from PinAPI.PinAPI import Pin_api
import uvicorn

def main():
    pin_api = Pin_api(name = "pin api", 
                      api_url="http://[your-home-assistant-ip-adres]:8123/api/", 
                      token="[your-home-assistant-long-life-token]",
                      pin_pw_list={25:"ok", 10: "test"})
    
    uvicorn.run(pin_api.app, host='0.0.0.0', port=11411)

if __name__ == "__main__":
    main()