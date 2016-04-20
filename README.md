# xiboside
A Xibo Player for Linux (probably other platform where Python, Qt, and MPlayer are available)



### Requirements:
xiboside requires Python2, [suds](https://fedorahosted.org/suds/), [PySide](http://wiki.qt.io/PySide), and [MPlayer](http://www.mplayerhq.hu/)

On Ubuntu 14.04, this line will satisfy the dependencies:  
`sudo apt-get install python-suds python-pyside mplayer`

.

### Running xiboside
```
xiboside`  
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
* getResource.

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

