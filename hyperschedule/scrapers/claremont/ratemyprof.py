from lxml import etree
import re
import requests
headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/75.0.3770.142 Safari/537.36'
}
INFO_NOT_AVAILABLE = 'Info currently not available'
TEACHER_LIST = []
TAG_FEEDBACK_LIST = []
RATING_LIST = []
TAKE_AGAIN_LIST = []
class RateMyProfAPI:
    def __init__(self, schoolName='Harvey Mudd College', teacher='staff'):
        '''
        Initialize the rate my professor API.
               The school code for where you want the professor's name to be checked.
        :param teacher: teacher's full name. if the teacher's name is not available,
                        default will be staff.
        '''
        if teacher != 'staff':
            teacher = str(teacher).replace(' ', '+')
        else:
            teacher = ''
        self.page_data = ''
        self.tag_feed_back = ''
        self.rating = ''
        self.take_again = ''
        self.profile_url = ''
        self.teacher_name = teacher
        self.index = -1
        if schoolName in ['CMC', 'cmc', 'Claremont', 'kenna', 'Kenna', 'Claremont McKenna College']:
            self.schoolName = 'Claremont McKenna College'
        elif schoolName in ['Scripps', 'SC', 'sc', 'scripps', 'scr', 'Scripps College']:
            self.schoolName = 'Scripps College'
        elif schoolName in ['Pomona', 'pomona', 'pc', 'PC', 'pom', 'Pomona College']:
            self.schoolName = 'Pomona College'
        elif schoolName in ['Pitzer', 'pz', 'PZ', 'Pitzer College', 'pitzer', 'pitzer college']:
            self.schoolName = 'Pitzer College'
        else:
            self.schoolName = 'Harvey Mudd College'
        schoolids = {'Claremont McKenna College': 234, 'Pomona College':774, 'Pitzer College':768, 'Scripps College':889, 'Harvey Mudd College':400}
        self.school_id = schoolids[self.schoolName]
        schoolnames = {}
        if self.teacher_name in TEACHER_LIST:
            self.index = TEACHER_LIST.index(self.teacher_name)
        else:
            TEACHER_LIST.append(self.teacher_name)

    def fetch_info(self):
        '''
        :function: initialize the RateMyProfessor data by making 2 HTTP requests
        '''
        #If professor showed as 'staff'
        if self.teacher_name == '':
            self.rating = INFO_NOT_AVAILABLE
            self.take_again = INFO_NOT_AVAILABLE
            self.tag_feed_back = []
            RATING_LIST.append(INFO_NOT_AVAILABLE)
            TAKE_AGAIN_LIST.append(INFO_NOT_AVAILABLE)
            TAG_FEEDBACK_LIST.append(INFO_NOT_AVAILABLE)
            return
        if self.index == -1:
            #making request to the RMP page
            url = 'https://www.ratemyprofessors.com/search.jsp?queryoption=HEADER&queryBy=teacherName' \
                  '&schoolName={name}' \
                  '&schoolID={id}&query={teacher}'.format(name='+'.join(self.schoolName.split(' ')), id=str(self.school_id), teacher='+'.join(self.teacher_name.split(' ')))
            page = requests.get(url=url, headers=headers)
            self.page_data = page.text
            page_data_temp = re.findall(r'ShowRatings\.jsp\?tid=\d+', self.page_data)
            if page_data_temp:
                page_data_temp = re.findall(r'ShowRatings\.jsp\?tid=\d+', self.page_data)[0]
                final_url = 'https://www.ratemyprofessors.com/' + page_data_temp
                if(final_url):
                    self.profile_url = final_url
                else:
                    self.profile_url = INFO_NOT_AVAILABLE
                self.tag_feed_back = []
                page = requests.get(final_url)
                document = etree.HTML(page.text)
                # Get tags
                tags = document.xpath('//*[@id="root"]/div/div/div[2]/div[1]/div[1]/div[5]/div[2]/span/text()')
                if not tags:
                    self.tag_feed_back = []
                else:
                    self.tag_feed_back = tags
                # Get rating
                self.rating = document.xpath('//*[@id="root"]/div/div/div[2]/div[1]/div[1]/div[1]/div[1]/div/div[1]/text()')[0]
                # Get 'Would Take Again' Percentage
                take_again = document.xpath('//*[@id="root"]/div/div/div[2]/div[1]/div[1]/div[3]/div[1]/div[1]/text()')
                if not take_again:
                    self.take_again = INFO_NOT_AVAILABLE
                else:
                    take_again = re.findall(r'\d+%', take_again[0])
                    if not take_again:
                        self.take_again = INFO_NOT_AVAILABLE
                    else:
                        self.take_again = take_again[0]
            else:
                # page not found
                self.rating = INFO_NOT_AVAILABLE
                self.take_again = INFO_NOT_AVAILABLE
                self.tag_feed_back = []
            RATING_LIST.append(self.rating)
            TAKE_AGAIN_LIST.append(self.take_again)
            TAG_FEEDBACK_LIST.append(self.tag_feed_back)
        else:
            self.rating = RATING_LIST[self.index]
            self.take_again = TAKE_AGAIN_LIST[self.index]
            self.tag_feed_back = TAG_FEEDBACK_LIST[self.index]
    def get_rating(self):
        '''
        :return: RMP rating.
        '''
        return INFO_NOT_AVAILABLE if self.rating == INFO_NOT_AVAILABLE else self.rating + '/5.0'
    def get_tags(self):
        '''
        :return: teacher's tag in [list]
        '''
        return self.tag_feed_back
    def get_first_tag(self):
        '''
        :return: teacher's most popular tag [string]
        '''
        return self.tag_feed_back[0] if self.tag_feed_back else INFO_NOT_AVAILABLE
    def get_would_take_again(self):
        '''
        :return: teacher's percentage of would take again.
        '''
        return self.take_again
    def get_url(self):
        '''
        :return: url to RateMyProfessor profile
        '''
        return self.profile_url
