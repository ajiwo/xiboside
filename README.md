# xiboside
A Xibo Player for Linux (probably other platform where Python, Qt, and MPlayer are available)


### Installation:

#### Install required packages
On Ubuntu 18.04:
`sudo apt install python3.7-dev python3.7-venv mplayer`

#### Download
```
git clone https://github.com/ajiwo/xiboside
cd xiboside
git checkout py37
```
#### Setup virtualenv
```
python3.7 -m venv /home/me/env-01
source /home/me/env-01/bin/activate
# cd /path/to/xiboside
pip3.7 install -r requirements.txt
```
Then, optionally, replace the default python interpreter by replacing the first line of `xiboside` file

`#!/usr/bin/env python` to `#!/home/me/env-01/bin/python3.7`

### Running xiboside
```
xiboside
```
```
  The configuration file xiboside_config.json is not exists  
  Creating default configuration...  
  Please edit the 'xiboside_config.json' file and then rerun xiboside again
```

From the generated configuration, edit the `url`, `serverKey`, and `cmsTzOffset`  
* `url`: the url of xibo-cms, example: http://myxibohost.com
* `serverKey`: the CMS secret key, it should be set on the Setting (http://myxibohost.com/index.php?p=admin) page of the version 1.7 of xibo-cms
* `cmsTzOffset`: my timezone is GMT+7, so I put 25200 (7 x 3600), if yours is GMT-7, put -25200
* You can leave the other parts unless you know what you're doing.

If you have edited the configuration file and placed it on other location, invoke xiboside with:  
`xiboside -c /path/to/config.cfg`  

If that `/path/to/config.cfg` is not there, xiboside will write the default configuration to that file.


Note:  
On the CMS, you need to set the display Settings Profile to Android  
`Display -> Edit -> Advanced -> Settings Profile -> Android`


### Spec Notes
Implemented xmds verbs: 
* registerDisplay
* requiredFiles
* schedule
* getFile
* getResource

Unimplemented xlf handling:
* layout z-index, region z-index
* schedule priority
* schedule ordering (play only the first found schedule)
* layout background image
* you tell me...

Supported Media type:
* Video (always scaled, aspect ratio ignored)
* Webpage: native, embedded, text, clock
* Image (always scaled, aspect ratio ignored)


