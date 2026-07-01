import utility

def get_grains(collect_info):
    """
    수집할 URL목록을 반환하는 함수 ( glean : 줍다 )
    """
    print(f"CALLBACK_URL:{collect_info['callback_url']}")
    url_list = utility.generate_combined_urls(collect_info['callback_url'])

    return url_list