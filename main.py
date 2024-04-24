from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
from selenium_recaptcha_solver import RecaptchaSolver
import time
import datetime
import logging
import json
import zipfile
import csv

# Initialize logger
logging.basicConfig(filename='tennis_odds_scraper.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(message)s')

with open('config.json') as config_data:
    config = json.load(config_data)

# service = ChromeService(ChromeDriverManager().install())
# optionBetplay = Options()
# optionBetplay.add_experimental_option("debuggerAddress", "127.0.0.1:9015")
# optionBetplay.add_argument("user-agent=Chrome/121.0.6167.185")
# driver = webdriver.Chrome(service=service, options=optionBetplay)
# wait = WebDriverWait(driver, 10)

# URLs for navigation
login_url = "https://www.pinnacle.com/en/account/login/"
match_url = "https://www.pinnacle.com/en/live/overview/"

with open('config.json') as config_data:
        config = json.load(config_data)

proxy_ip = config['proxy_ip']
proxy_port = config['proxy_port']
proxy_user = config['proxy_user']
proxy_pass = config['proxy_pass']

manifest_json = """
{
    "version": "1.0.0",
    "manifest_version": 2,
    "name": "Proxy Exctension",
    "permissions": [
        "proxy",
        "tabs",
        "unlimitedStorage",
        "storage",
        "<all_urls>",
        "webRequest",
        "webRequestBlocking"
    ],
    "background": {
        "scripts": ["background.js"]
    },
    "minimum_chrome_version":"22.0.0"
}
"""

background_js = """
var config = {
        mode: "fixed_servers",
        rules: {
        singleProxy: {
            scheme: "http",
            host: "%s",
            port: parseInt(%s)
        },
        bypassList: ["localhost"]
        }
    };
chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
function callbackFn(details) {
    return {
        authCredentials: {
            username: "%s",
            password: "%s"
        }
    };
}
chrome.webRequest.onAuthRequired.addListener(
            callbackFn,
            {urls: ["<all_urls>"]},
            ['blocking']
);
""" % (proxy_ip, proxy_port, proxy_user, proxy_pass)
    
def init_driver_chrome():
    pluginfile = 'proxy_auth_plugin.zip'

    with zipfile.ZipFile(pluginfile, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)
    custom_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
    service = ChromeService(ChromeDriverManager().install())
    chrome_options = Options()
    chrome_options.add_extension(pluginfile)
    chrome_options.add_argument('--ignore-ssl-errors=yes')
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--allow-insecure-localhost')  
    chrome_options.add_argument(f"user-agent={custom_user_agent}") 
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def login_to_site(driver, login_url):
    try:
        driver.get(login_url)
        username_input = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, '[placeholder="Email or ClientID"]')))
        password_input = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, '[placeholder="password"]')))
        
        with open('config.json') as config_data:
            configData = json.load(config_data)

        username_input.send_keys(configData["login_username"])
        password_input.send_keys(configData["login_pass"])
        password_input.send_keys(Keys.RETURN)
        time.sleep(2)
        
        g_recaptcha = None
        try:
            g_recaptcha = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'g-recaptcha'))
            )
            print('reCAPTCHA iframe detected.')
        except Exception as e:
            logging.error(f"No reCAPTCHA iframe found, proceeding: {str(e)}")
            scrap_data(driver)
            return 

        if g_recaptcha:
            solver = RecaptchaSolver(driver)
            recaptcha_iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//iframe[@title="reCAPTCHA"]'))
            )
            solver.click_recaptcha_v2(iframe=recaptcha_iframe)
            time.sleep(15)
            submit_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))
            )
            submit_btn.click()

            print("CAPTCHA solved and login button clicked.")
            time.sleep(5)  
            scrap_data(driver)
    except Exception as e:
        logging.error(f"Error during login: {str(e)}")
        driver.quit()
        
def scrap_data(driver):
    driver.get(match_url)
    try:
        all_buttons = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "style_tabItem__2Y054"))
        )

        tennis_button_found = False

        for tab_btn in all_buttons:
            try:
                btn_text = tab_btn.find_element(By.CLASS_NAME, "style_tabLabel__1_d9j").text
                if btn_text == "TENNIS":
                    tab_btn.click()
                    tennis_button_found = True
                    break 
            except Exception as e:
                print(f"Error finding button text: {e}")
                continue 

        if not tennis_button_found:
            print("TENNIS button not found")
    except Exception as e:
        print(f"An error occurred while processing buttons: {e}")
        
    try:
        with open('live_betting_data.csv', 'x', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Timestamp', '1st Player', '2nd Player', '1st Money Line', '2nd Money Line'])
    except FileExistsError:
        pass

    last_data = {}

    try:
        while True:
            try:
                live_betting_lists = WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CLASS_NAME, "style_row__12oAB"))
                )

                current_data = {}
                for index, live_betting_element in enumerate(live_betting_lists):
                    try:
                        player_names = live_betting_element.find_elements(By.CLASS_NAME, "style_participant__2BBhy")
                        money_lines = live_betting_element.find_elements(By.CLASS_NAME, "style_button__G9pbN")
                        current_time = datetime.datetime.now()
                        formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
                        player_names_1 = player_names[0].text if len(player_names) > 0 else "Unknown"
                        player_names_2 = player_names[1].text if len(player_names) > 1 else "Unknown"
                        money_lines_1 = money_lines[0].text if len(money_lines) > 0 else "No Odds Available"
                        money_lines_2 = money_lines[1].text if len(money_lines) > 1 else "No Odds Available"
                        print(f"${formatted_time} -----> Player name is ${player_names_1} :: ${player_names_2} [Money line is ${money_lines_1} :: ${money_lines_2}]")

                        key = (player_names_1, player_names_2)
                        current_data[key] = (money_lines_1, money_lines_2)

                    except StaleElementReferenceException:
                        # Re-fetch the list to handle stale element
                        live_betting_lists = WebDriverWait(driver, 10).until(
                            EC.presence_of_all_elements_located((By.CLASS_NAME, "style_row__12oAB"))
                        )
                        live_betting_element = live_betting_lists[index]
                        continue

                changes = {key: val for key, val in current_data.items() if key not in last_data or last_data[key] != val}
                current_time = datetime.datetime.now()
                formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
                print(f"Changed : ${formatted_time} -----> ${changes}")
                
                if changes:
                    with open('live_betting_data.csv', 'a', newline='') as file:
                        writer = csv.writer(file)
                        for key, value in changes.items():
                            current_time = datetime.datetime.now()
                            formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
                            writer.writerow([formatted_time, key[0], key[1], value[0], value[1]])

                last_data = current_data

                time.sleep(1)

            except Exception as e:
                print(f"An error occurred: {e}")

    except Exception as e:
        print(f"An error occurred: {e}")

def main():
    driver = init_driver_chrome()
    login_to_site(driver, login_url)
    is_logged_in = True 

    while True:
        try:
            if is_logged_in:
                scrap_data(driver)
            else:
                login_to_site(driver, login_url)
                is_logged_in = True 
        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
            if 'session expired' in str(e).lower(): 
                is_logged_in = False  
            else:
                break 
        time.sleep(10)
    
if __name__ == '__main__':
    main()
