import praw

from postgen import get_post


def get_reddit():
	r = praw.Reddit(user_agent='A script for /r/PokemonGOToronto (currently in testing)')



	return r

def get_reddit_post(r):
	post = r.get_info(thing_id='t3_4sf8ah')

if __name__ == '__main__':
    post = get_post()
    print(post)
