# Teachable downloader

Few words about the motivation behind the project. I've subscribed to one of the
services powered by Teachable, and watch recorded lectures there. The problem
for me is that I prefer to listen it on the go during cycling, on mobile phone, when
the screen is off. Unfortunately it stops playing when I turn off the screen, so
I prefer to download it somewhere (to telegram for example) and use external player.

The project is rather simple, what it does is next:
* Uses browser automation to log in to the system, scrape the pages for video and pdf content. 
[selenium-wire](https://pypi.org/project/selenium-wire/) is used because, to my knowledge, it's the only project here to intercept https on top of geckodriver with ease.
* Then it run [streamlink](https://streamlink.github.io/) to download the .ts files.
* Then it uses [ffmpeg](https://ffmpeg.org/) to convert `.ts` file to `.mp4`.
* Then it calls [telegram-upload](https://github.com/Nekmo/telegram-upload) to push files to telegram.

All the above requirements should be fulfilled.
