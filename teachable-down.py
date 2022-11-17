from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import json
import subprocess
import requests
import re
import argparse

class TeachableDownloader:
    def __init__(self, root_url, email, password, debug):
        self.root_url = root_url
        self.driver = webdriver.Firefox()
        self.email = email
        self.password = password
        self.debug = debug

        # prepare download dir
        self.download_dir = "downloads"
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)


    def login(self):
        driver = self.driver

        driver.get(self.root_url)

        el = driver.find_element(by=By.XPATH, value="//a[@href='/sign_in']")
        el.click()
        print("clicked login")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//input[@name='email']"))
        )
        el = driver.find_element(by=By.XPATH, value="//input[@name='email']")
        el.send_keys(self.email)
        el = driver.find_element(by=By.XPATH, value="//input[@name='password']")
        el.send_keys(self.password)
        # sleep 2 sec to make captcha happy
        driver.implicitly_wait(3)  # didn't help, so call sleep
        time.sleep(3)
        # send enter
        el.send_keys("\ue007")

        # wait for By.css('a.fedora-navbar-link.navbar-link')
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "a.fedora-navbar-link.navbar-link")
            )
        )
        print("logged in")

    def scrape_lectures(self, course):
        """Returns json array with: section, lecture, url"""
        result = []
        driver = self.driver
        course_url = "{}/courses/enrolled/{}".format(self.root_url, course)
        driver.get(course_url)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.col-sm-12.course-section")
            )
        )
        print("course page loaded")

        sections = driver.find_elements(
            by=By.CSS_SELECTOR, value="div.col-sm-12.course-section"
        )
        print("sections found {}".format(len(sections)))
        for section in sections:

            section_title = section.find_element(
                by=By.CSS_SELECTOR, value="div.section-title"
            ).text
            print("section: {}".format(section_title))

            lectures = section.find_elements(
                by=By.CSS_SELECTOR, value="li.section-item"
            )
            print("lectures size {}".format(len(lectures)))
            for lecture in lectures:
                lecture_title = lecture.find_element(
                    by=By.CSS_SELECTOR, value="span.lecture-name"
                ).text
                href = lecture.find_element(
                    by=By.CSS_SELECTOR, value="use"
                ).get_attribute("xlink:href")
                if href != "#icon__Video":
                    # skip all non video lectures
                    continue
                print("  {}".format(lecture_title))

                lecture_url = lecture.find_element(
                    by=By.CSS_SELECTOR, value="a.item"
                ).get_attribute("href")

                result.append(
                    {
                        "section": section_title,
                        "lecture": lecture_title,
                        "url": lecture_url,
                    }
                )

        return result

    def get_requests(self):
        driver = self.driver
        result = []
        for request in driver.requests:
            if request.response:
                result.append((request.url, request.response.status_code))
        if self.debug:
        # write to file
            with open("requests.txt", "w") as f:
                for url, status in result:
                    f.write("{} {}\n".format(status, url))
        return result

    def del_requests(self):
        del self.driver.requests

    def __del__(self):
        if not self.debug: # leave window open if debug
            self.driver.quit()

    def get_courses(self):
        courses = []
        driver = self.driver
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.course-listing")
            )
        )
        print("courses page loaded")
        course_list = driver.find_elements(
            by=By.CSS_SELECTOR, value="div.course-listing"
        )
        print("courses found {}".format(len(course_list)))
        for course in course_list:
            course_id = course.get_attribute("data-course-id")
            course_title = course.find_element(
                by=By.CSS_SELECTOR, value="div.course-listing-title"
            ).text
            print("course: {} {}".format(course_id, course_title))
            courses.append(course_id)

        return courses

    def get_lectures(self, courses):
        result = []
        for course in courses:
            # check if lectures are cached
            cache_file = "lectures_{}.json".format(course)
            if self.debug and os.path.exists(cache_file):
                print("{} found using the cache".format(course))

                with open(cache_file, "r") as f:
                    lectures = json.load(f)
                    result += lectures
            else:
                lectures = self.scrape_lectures(course)
                result += lectures
                if self.debug:
                    with open(cache_file, "w") as f:
                        json.dump(lectures, f)
        return result

    def download_lectures(self, lectures):
        def get_filename(lecture):
            name = lecture["lecture"]
            # normalize name
            if "«" in lecture["lecture"] and "»" in lecture["lecture"]:
                name = name[name.find("«") + 1 : name.find("»")]
            if '"' in name:
                # extract name from "name"
                name = name[name.find('"') + 1 : name.rfind('"')]
            # remove time "(00:00)" or "(00:00 )" at the end
            name = re.sub(r"\(\d\d:\d\d\s*\)?\s*$", "", name)
            # trim spaces
            name = name.strip()

            # extract eveything inside '«' and '»'
            # create a map
            section_remap = {
                "Добро пожаловать в программу": "Onboarding",
                "Студия College для подростков": "College",
                "Практическая психология": "Psychology",
                "Q&A сессия": "QnA",
            }
            section = lecture["section"]
            if section in section_remap:
                section = section_remap[section]

            # remove lecture["section"] from name
            name = name.replace(lecture["section"], "")

            # replace special characters for file system
            spec_syms = {
                "/": "_",
                "\\": "_",
                ":": "_",
                "*": "_",
                "?": "_",
                '"': "_",
                "<": "_",
                ">": "_",
                "|": "_",
                "—": "-",
            }
            for k, v in spec_syms.items():
                name = name.replace(k, v)
            name = "#{} {}".format(section, name)
            # cut everything after 127 symbols, to fit path limit (127 cyrylic symbols max)
            if len(name) > 123:
                name = name[:122] + "_"
            return name

        proceeded = []
        file_path_processed = os.path.join(self.download_dir, "processed.json")
        if os.path.exists(file_path_processed):
            with open(file_path_processed, "r") as f:
                proceeded = json.load(f)
        #
        # cycle through lectures
        for lecture in lectures:
            raw_name = get_filename(lecture)
            l = [self.download_dir, raw_name]
            file_path = os.path.join(*l)
            file_path_pdf = file_path + ".pdf"
            file_path_ts = file_path + ".ts"
            file_path_mp4 = file_path + ".mp4"

            if file_path_mp4 in proceeded:
                print("already proceeded {}".format(file_path_mp4))
                continue

            if os.path.exists(file_path_mp4):
                print("already downloaded {}".format(file_path_mp4))
                proceeded.append(file_path_mp4)
                continue

            print(
                "downloading {}: {}".format(
                    lecture["section"], lecture["lecture"]
                )
            )
            print("file_path = {}".format(file_path))

            self.del_requests()
            driver = self.driver
            driver.get(lecture["url"])

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "lecture_heading"))
            )
            # wait additional 2 sec
            time.sleep(5)
            # get requests
            requests_log = self.get_requests()
            pdf_url = ""
            for url, _ in requests_log:
                if url.startswith(
                    "https://cdn.filestackcontent.com/preview=css"
                ):
                    pdf_url = url
                    break

            if pdf_url and not os.path.exists(file_path_pdf):

                print("pdf_url = {}".format(pdf_url))
                # remove /preview=css:.../ from url
                pdf_url = re.sub(r"preview=css:.*?/", "", pdf_url)
                print("pdf_url = {}".format(pdf_url))
                # download pdf
                r = requests.get(pdf_url)
                with open(file_path_pdf, "wb") as f:
                    f.write(r.content)
                print("pdf saved")

            video_url = ""

            for url, _ in requests_log:
                if "master" in url and "m3u8" in url:
                    video_url = url
                    break

            if not video_url:
                print("video_url not found")
                exit(1)

            # execute streamlink
            cmd = [
                "streamlink",
                video_url,
                "best",
                "-o",
                file_path_ts,
                "--hls-live-restart",
                "--hls-segment-threads",
                "10",
            ]
            print("executing: {}".format(" ".join(cmd)))
            subprocess.call(cmd)

            # convert to mp4 with ffmpeg
            cmd = [
                "ffmpeg",
                "-i",
                file_path_ts,
                "-c",
                "copy",
                file_path_mp4,
            ]
            print("executing: {}".format(" ".join(cmd)))
            subprocess.call(cmd)

            os.remove(file_path_ts)

            for f in [file_path_pdf, file_path_mp4]:
                if os.path.exists(f):
                    # execute telegram-upload {file_path}
                    cmd = [
                        "telegram-upload",
                        f,
                    ]
                    print("executing: {}".format(" ".join(cmd)))
                    subprocess.call(cmd)
                proceeded.append(f)

        # save proceeded files to downloads/proceeded.json
        with open(file_path_processed, "w") as f:
            json.dump(proceeded, f)

    def run(self):
        self.login()
        courses = self.get_courses()
        lectures = self.get_lectures(courses)
        self.download_lectures(lectures)


def main():
    # parse args with argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        help="Root course url",
        required=True
    )
    parser.add_argument(
        "--debug",
        help="Debug mode",
        action="store_true"
    )
    parser.add_argument(
        "--creds",
        help="Email:password from env vars DL_CREDS"
    )
    args = parser.parse_args()
    # get email and password
    if args.creds:
        email, password = args.creds.split(":")
    else:
        email, password = os.environ["DL_CREDS"].split(":")
    if not email or not password:
        print("Email or password is empty, use --creds or DL_CREDS env var")
        exit(1)
    print("Scraping {}, using login: {}".format(args.root, email))

    teachable = TeachableDownloader(args.root, email, password, args.debug)
    teachable.run()

if __name__ == "__main__":
    main()
