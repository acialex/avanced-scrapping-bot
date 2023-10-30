from selenium import webdriver
#from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time
import csv

START_URL = 'https://www.pasion.com/contactos-mujeres-en-cantabria/'

class ProxyRequester(object):
    def __init__(self, change_ip_after=10):
        # value which determines after how many requests a new ip address should be used
        self.change_ip_after = change_ip_after
        # variable to keep track of number of requests made before last ip change
        self.request_count = 0
        self.__instantiate_new_driver()

    def __del__(self):
        '''Close driver when Class gets destroyed'''
        if hasattr(self, 'driver'):
            self.driver.quit()

    def __instantiate_new_driver(self):
        '''Closes old driver if exists and instantiates a new one to get a new ip address'''
        if hasattr(self, 'driver'):
            self.driver.close()
        self.driver = self.__get_chrome_driver()

    def __get_chrome_driver(self): #, proxy):
        '''Returns a new Chrome driver with proxy setting configured'''
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_extension('proxy_auth_plugin.zip')
        driver = webdriver.Chrome(chrome_options=chrome_options)
        return driver

    def __check_for_tunnel_connection_error(self):
        '''
        Detect whether a ERR_TUNNEL_CONNECTION_FAILED error was thrown. 
        If yes, retry after a certain amount of time 
        '''
        try:
            self.driver.find_element_by_xpath('.//*[text()[contains(., "ERR_TUNNEL_CONNECTION_FAILED")]]')
            return True
        except NoSuchElementException:
            '''If there is no Error on the HTML-Page just return without doing anything'''
            return False

    def get(self, url):
        '''Makes get requests and restarts driver with new proxy automatically after set amount of requests'''
        self.request_count += 1
        # if the number of get requests is higher than the 
        if self.request_count >= self.change_ip_after:
            self.__instantiate_new_driver()
            self.request_count = 0
            print(self.request_count)
        self.driver.get(url)
        if self.__check_for_tunnel_connection_error():
            print('ERR_TUNNEL_CONNECTION_FAILED', url, self.request_count)
            self.request_count -= 1
            time.sleep(1)
            self.get(url)

    def xpath(self, query, wait_time=None):
        '''
        Convenience wrapper around webdrivers find_elements_by_xpath method
        @query xpath query to be executed
        @wait_time time to wait for element to load
        @yield strings found with the specified xpath
        '''
        if isinstance(wait_time, int) or isinstance(wait_time, float):
            WebDriverWait(self.driver, wait_time).until(
                EC.presence_of_element_located(
                    (By.XPATH, query)
                )
            )
        for element in self.driver.find_elements_by_xpath(query):
            yield element.text

class PasionScraper(object):
    def __init__(self, link):
        options = Options()
        # you can add this line to make the browser "invisible":
        options.add_argument('-headless')
        self.driver = webdriver.Chrome(options=options)
        self.driver.get(link)

    def __del__(self):
        self.driver.quit()

    def get_contacts(self):
        '''Gets all contcacts found in category page '''
        self.contact_ids = []
        while True:
            # writes all contact ids from category page to self.contact_ids
            self.__get_contact_ids()
            #break # would break after first page of category, useful for testing
            try:
                # go to the next category page and continue the loop
                self.__go_to_next_page()
            except:
                # if there is no link to a next page anymore, the loop breaks 
                break
        # prints the number of contact ids found
        print(len(self.contact_ids))
        for contact in self.__get_contacts():
            yield contact
            
    def __get_contact_ids(self):
        '''Writes all contact ids from a category page to self.contact_ids'''
        self.__confirm_age(self.driver)
        for element in self.driver.find_elements_by_xpath('//div[@class="x1"]'):
            _id = element.find_element_by_xpath('.//*[text()[contains(., "Contactar")]]/ancestor::a').get_attribute('href').split("'")[1]
            # check if id is not already in self.contact_ids to avoid duplicates
            if _id not in self.contact_ids:
                print(_id)
                self.contact_ids.append(_id)

    def __go_to_next_page(self):
        '''Finds and clicks the link to the next page of the current category'''
        self.driver.find_element_by_xpath('//a[text()[contains(., "Siguiente")]]').click()
        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located(
                (By.CLASS_NAME, "x1")
            )
        )

    def __get_contacts(self):
        '''
        Loop through every id for every contact
        Constructs a url from every id and makes a request
        Extracts names and phone numbers
        Yields dictionary with id + scraped data
        '''
        requester = ProxyRequester()
        self.__confirm_age(driver=requester.driver)
        for _id in self.contact_ids:
            contact_data_url = 'https://www.pasion.com/datos-contacto/?id=' + _id
            requester.get(contact_data_url)    
            if self.__has_phone_number(requester.driver):
                try: 
                    # some contact infos have no name to them
                    name = list(requester.xpath(('.//div[@class="texto"]/div/strong')))
                except NoSuchElementException:
                    name = ''
                phone_numbers = list(requester.xpath('.//div[@class="telefonos"]'))
                yield {
                    "id": _id,
                    "name": name,
                    "phone_number": phone_numbers
                }
        
    def __has_phone_number(self, contact_window):
        '''
        Check if phone numbers are on page
        If yes returns True
        else returns False
        '''
        try:
            WebDriverWait(contact_window, 1).until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, "telefonos")
                )
            )
            return True
        except TimeoutException:
            return False
        
    def __confirm_age(self, driver):
        '''Sometimes the page asks if you are old enough to visit. If so a link must be clicked'''
        try:
            driver.find_element_by_xpath('//a[@href="javascript:muestradulto()"]').click()
        except NoSuchElementException:
            '''If there is no question about our age the button isn't there as well so an Exception is thrown which we have to ignore'''
            return

def run_scraper(category_url):
    pasion_scraper = PasionScraper(category_url)
    # Gets every contact as dictionary with fields id, name, phone_number
    to_csv = []
    for contact in pasion_scraper.get_contacts():
        print(contact)
        to_csv.append(contact)

    # create the csv and write all found contacts to the file out.csv
    with open('out.csv', 'w', newline='') as outfile:
        wr = csv.writer(outfile, quoting=csv.QUOTE_ALL)
        wr.writerow(['id', 'name', 'phone_number'])
        for row in to_csv:
            name = row['name']
            if len(name) == 1:
                name = row['name'][0]
            wr.writerow([row['id'], name, row['phone_number']])

if __name__ == "__main__":
    run_scraper(START_URL)
