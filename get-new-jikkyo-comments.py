from websockets import typing
from io import BufferedReader
from typing import List, Optional
from peewee import DateTimeField, IntegerField, SqliteDatabase,Model, TextField
import argparse
import asyncio
import copy
import dataclasses
import datetime
import html
import json
import logging
import math
import os
import re
import traceback
import types
import urllib.parse
import urllib.request
import websockets

logging.basicConfig(level=logging.INFO, format='%(asctime)s: %(message)s',stream=None)
logging.getLogger('websockets').setLevel(logging.ERROR)
logging.getLogger('peewee').setLevel(logging.ERROR)
logger = logging.getLogger()

@dataclasses.dataclass(frozen=True)
class ChannelDefine:
    jkNumber:int
    cliName:str
    sqliteFileName:str
    serviceId:List[int]
channelDefs = [
    ChannelDefine(jkNumber=  1,cliName="NHK-G",sqliteFileName="jk1 NHK総合"    ,serviceId=[0x0400]),
    ChannelDefine(jkNumber=  2,cliName="NHK-E",sqliteFileName="jk2 NHK教育"    ,serviceId=[0x0408]),
    ChannelDefine(jkNumber=  4,cliName=  "NTV",sqliteFileName="jk4 日本テレビ"  ,serviceId=[0x0410]),
    ChannelDefine(jkNumber=  5,cliName=   "EX",sqliteFileName="jk5 テレビ朝日"  ,serviceId=[0x0428]),
    ChannelDefine(jkNumber=  6,cliName=  "TBS",sqliteFileName="jk6 TBS"        ,serviceId=[0x0418]),
    ChannelDefine(jkNumber=  7,cliName=   "TX",sqliteFileName="jk7 テレビ東京"  ,serviceId=[0x0430]),
    ChannelDefine(jkNumber=  8,cliName=   "CX",sqliteFileName="jk8 フジテレビ"  ,serviceId=[0x0420]),
    ChannelDefine(jkNumber=  9,cliName=   "MX",sqliteFileName="jk9 TOKYO MX"   ,serviceId=[0x5C38]),
    ChannelDefine(jkNumber=211,cliName= "BS11",sqliteFileName="jk211 BSイレブン",serviceId=[0x00D3]),
]
class Chat(Model):
    # 旧ニコ実方式との違いは、threadをint->strに。lvId(str)を追加
    thread = TextField(column_name="thread")
    lvId = TextField(column_name="lv_id")
    jkId = IntegerField(column_name="jk_id")
    no = IntegerField(column_name="no")
    vpos = IntegerField(column_name="vpos",null=True)
    date = IntegerField(column_name="date")
    mail = TextField(column_name="mail")
    name = TextField(column_name="name")
    userId = TextField(column_name="user_id")
    anonymity = IntegerField(column_name="anonymity",null=True)
    deleted = IntegerField(column_name="deleted",null=True)
    dateUsec = IntegerField(column_name="date_usec",null=True)
    premium = IntegerField(column_name="premium",null=True)
    locale = TextField(column_name="locale")
    xmlText = TextField(column_name="xml_text")
    class Meta:
        table_name = "chat"
        indexes =  (
            (('thread', 'jkId',"no",), True),
            (('date',), False),
        )
class TimeShiftLog(Model):
    lvId = TextField(column_name="lv_id",primary_key=True)
    title = TextField(column_name="title")
    firstCheckDate = DateTimeField(column_name="created_at")
    lastCheckDate = DateTimeField(column_name="updated_at")

class JkTxt:
    # tsファイルから日時とチャンネルを読み込み、ログのsqliteファイルから、コメントのjkTxtを作成し、指定のパスに設置する
    def __init__(self,tsFilePath:str,exportJkPath:str):
        self.tsFilePath = tsFilePath
        self.exportJkPath = exportJkPath
    def getData(self):
        (tsStartTime,tsDuration,serviceId) = self._getTsFileInfo()
        serviceData = self._getServiceIdData(serviceId)
        sqliteFilePath = f"./logs-nicolive/{serviceData.sqliteFileName}.sqlite3"
        chats = self._getCommentDatas(sqliteFilePath,tsStartTime,tsDuration.total_seconds())
        logTextTime = f"{tsStartTime:%Y/%m/%d %H:%M:%S} ～ {int(tsDuration.total_seconds() / 60)}分{int(tsDuration.total_seconds() % 60):02}秒"
        if len(chats) == 0:
            # 2020/01/01 00:00:00 ～ 30:00 NHK-G から 123 コメント保存 xxxx.ts
            logger.info(f"{logTextTime} {serviceData.cliName} はコメントがありませんでした")
            return
        jkTxtPath = os.path.join(self.exportJkPath,f"jk{serviceData.jkNumber}",f"{int(tsStartTime.timestamp())}.txt")
        logger.info(f"{logTextTime} {serviceData.cliName} から {len(chats)} コメント保存 {self.tsFilePath} -> {jkTxtPath}")
        self._makeCommentJkTxt(jkTxtPath,chats,f"{tsStartTime:%Y/%m/%d %H:%M:%S} ～ {(tsStartTime+tsDuration):%Y/%m/%d %H:%M:%S} 0x{serviceId:04X} {serviceData.sqliteFileName}")
    def _getTsFileInfo(self):
        return ParseTs(self.tsFilePath).parse()
    def _getServiceIdData(self,serviceId:int) -> ChannelDefine:
        r = [i for i in channelDefs if (serviceId in i.serviceId )]
        if len(r) != 1:
            raise Exception(f"Service Id 0x{serviceId:04X} は非対応です")
        else:
            return r[0]
    def _getCommentDatas(self,sqliteFilePath:str,startDate:datetime.datetime,durationSec:float) -> typing.List[Chat]:
        db = SqliteDatabase(sqliteFilePath)
        chats = [] # type: typing.List[Chat]
        with db.bind_ctx([Chat]):
            fromTimestamp = startDate.timestamp() - 10
            toTimestamp = startDate.timestamp()+durationSec + 10
            for chat in (Chat.select().where(fromTimestamp <= Chat.date,Chat.date<=toTimestamp).order_by(Chat.date)):
                chats.append(chat)
        return chats
    def _makeCommentJkTxt(self,jkTxtPath:str,chats:typing.List[Chat],headerMemo:str):
        dirPath = os.path.dirname(jkTxtPath)
        tsFileName = os.path.basename(self.tsFilePath)
        os.makedirs(dirPath,exist_ok=True)
        # modeはxにすること
        with open(jkTxtPath,mode="w",encoding="utf-8") as f:
            # head
            f.write(f'<chat abone="1" thread="0" no="" date="" mail="shita" user_id="nicojk-timeshift">【ログ】{tsFileName} {headerMemo}</chat>\n')
            for chat in chats:
                f.write(f'<chat thread="{chat.thread}" no="{chat.no}" vpos="{chat.vpos}" date="{chat.date}" mail="{chat.mail}" user_id="{chat.userId}" anonymity="{chat.anonymity}">{chat.xmlText}</chat>\n')

class ParseTs:
    def __init__(self,tsFilePath:str):
        self.tsFilePath = tsFilePath
    def parse(self):
        with open(self.tsFilePath, 'rb') as r:
            r.seek(0,os.SEEK_END)
            fileSize = r.tell()
            r.seek(0,os.SEEK_SET)
            headInfo = self._getPidTot(r,fileSize,True)
            tailInfo = self._getPidTot(r,fileSize,False)
            if headInfo[1] != tailInfo[1]:
                raise Exception(f"ServiceIdの値がファイルの先頭と末尾で異なります")
            return (headInfo[0],tailInfo[0]-headInfo[0],headInfo[1])

    def _getPidTot(self,r:BufferedReader,fileSize:int,fromHead:bool):
        # http://jk.rutice.net/ より
        pos = 0 if fromHead == True else (fileSize - 188 - 188)
        addType = 1 if fromHead == True else -1
        pats = {} # type: types.Dict[int,int]
        totDateObj = None # type: typing.Optional[datetime.datetime]
        def readByte(pos:int,len:int) -> bytes:
            r.seek(pos,os.SEEK_SET)
            return r.read(len)
        while pos + 188 < fileSize and  0 <= pos:
            # sync
            packet = readByte(pos,189)
            if packet[0] != 0x47 or packet[188] != 0x47:
                pos +=  ( 1 * addType)
                continue
            # PID
            pid = (packet[1] * 256 + packet[2]) & 0x1FFF

            # PAT
            if pid == 0x00:
                p = packet
                adapSize = p[4]
                length = (p[adapSize+6] * 256 + p[adapSize+7]) & 0x0FFF
                forI = 13 + adapSize
                forU = 5+length-4-adapSize
                for i in range(forI,forU,4):
                    sid = p[i] *256 + p[i+1]
                    if sid > 0:
                        if sid in pats:
                            pats[sid] += 1
                        else:
                            pats[sid] = 1
                        
            # TOT
            if pid == 0x14:
                p = packet
                adaptSize = p[4]
                if p[adaptSize+5] == 0x70 or p[adaptSize+5] == 0x73:
                    ymd = p[adaptSize+8] * 256 + p[adaptSize+9]
                    ydash = math.floor((ymd * 20 - 301564) / 7305)
                    mdash = math.floor((ymd * 10000 - 149561000 - ydash * 1461 / 4 * 10000) / 306001)
                    #d = (mdash == 14 || mdash == 15) ? 1 : 0
                    d = 1 if mdash == 14 or mdash == 15 else 0
                    day = ymd - 14956 - math.floor(ydash * 1461 / 4) - math.floor(mdash * 306001 / 10000)
                    year = math.floor(ydash + d) + 1900
                    month = math.floor(mdash - 1 - d * 12)
                    hour = int(f"{p[adaptSize+10]:X}")
                    min = int(f"{p[adaptSize+11]:X}")
                    sec = int(f"{p[adaptSize+12]:X}")
                    dateTimeObj = datetime.datetime(year, month, day, hour, min,sec)
                    if totDateObj == None:
                        totDateObj = dateTimeObj
                    else:
                        # exit
                        patsCount = len(pats.keys())
                        if patsCount == 0:
                            raise Exception("PATが見つかりません")
                        elif 1 < patsCount :
                            raise Exception(f"PATが2個以上あります {pats}")
                        else:
                            return ( totDateObj,next(iter(pats.keys())) )
            pos += (188*addType)
        raise Exception(f"PAT TOTが見つかりません")
class DatabaseClass:
    @staticmethod
    def getSavedTimeShiftLogs(jkId:int) -> typing.List[TimeShiftLog]:
        sqliteFileName = jkIdToSqliteFileName(jkId)
        db = SqliteDatabase(f"./logs-nicolive/{sqliteFileName}.sqlite3")
        result = [] # type: typing.List[TimeShiftLog]
        with db.bind_ctx([TimeShiftLog]):
            db.create_tables([TimeShiftLog])
            for log in TimeShiftLog.select():
                result.append(log)
        return result

    @staticmethod
    def saveTimeShiftLog(jkId:int,lvAddress:str,title:str):
        sqliteFileName = jkIdToSqliteFileName(jkId)
        db = SqliteDatabase(f"./logs-nicolive/{sqliteFileName}.sqlite3")
        with db.bind_ctx([TimeShiftLog]):
            db.create_tables([TimeShiftLog])
            (TimeShiftLog
                .insert(lvId=lvAddress,title=title,firstCheckDate=datetime.datetime.now(),lastCheckDate=datetime.datetime.now())
                .on_conflict(
                    conflict_target=[TimeShiftLog.lvId],  # Which constraint?
                    preserve=[TimeShiftLog.lastCheckDate] )
                .execute())

    @staticmethod
    def saveXmlChat(jkId:int,lvAddress:str,chatList:typing.List):
        sqliteFileName = jkIdToSqliteFileName(jkId)
        db = SqliteDatabase(f"./logs-nicolive/{sqliteFileName}.sqlite3")
        with db.bind_ctx([Chat,TimeShiftLog]):
            db.create_tables([Chat,TimeShiftLog])
        insertManyVal :typing.List = []
        for chat_ in chatList:
            try:
                chat = copy.copy(chat_)
                def getIntMust(key:str) -> int:
                    """
                    特定のキーを必ず数値にする。要素が無い時はエラー
                    """
                    if key not in chat:
                        raise Exception(f"key {key} not found.")
                    valStr = chat[key]
                    chat.pop(key)
                    valInt = int(valStr)
                    return valInt
                def getIntOrNone(key:str) -> Optional[int]:
                    """
                    特定のキーを数値、もしくはNoneにする
                    """
                    if key not in chat:
                        return None
                    valStr = chat[key]
                    chat.pop(key)
                    if valStr == None:
                        return None
                    valInt = int(valStr)
                    return valInt
                def getStrOrEmpty(key:str) -> str:
                    """
                    特定のキーを文字列 (空文字あり)にする
                    """
                    if key not in chat:
                        return ""
                    valStr = chat[key]
                    chat.pop(key)
                    return valStr
                thread = getStrOrEmpty("thread")
                date = getIntMust("date")
                no = getIntMust("no")
                vpos = getIntOrNone("vpos")
                premium = getIntOrNone("premium")
                anonymity = getIntOrNone("anonymity")
                deleted = getIntOrNone("deleted")
                date_usec = getIntOrNone("date_usec")
                mail = getStrOrEmpty("mail")
                name = getStrOrEmpty("name")
                user_id = getStrOrEmpty("user_id")
                locale = getStrOrEmpty("locale")
                xmlText = getStrOrEmpty("content")
                if len(chat.keys()) != 0:
                    raise Exception(f"keyが残っています {chat}")
                insertManyVal.append({
                    'thread': thread,
                    'lvId': lvAddress,
                    'jkId': jkId,
                    'no': no,
                    'vpos': vpos,
                    'date': date,
                    'mail': mail,
                    'name': name,
                    'userId': user_id,
                    'anonymity': anonymity,
                    'deleted': deleted,
                    'dateUsec': date_usec,
                    'premium': premium,
                    'locale': locale,
                    'xmlText': xmlText,
                })
            except Exception as e:
                logger.error(f"{e}\n{traceback.format_exc()}")
                continue
        totalInsertCount = 0
        with db.bind_ctx([Chat]):
            with db.atomic():
                insertLimit = 2000
                for idx in range(0, len(insertManyVal), insertLimit):
                    insertSet = insertManyVal[idx:idx+insertLimit]
                    insertResult = (Chat.insert_many(insertSet).on_conflict_ignore().execute())
                    totalInsertCount += insertResult

class DownloadTimeShift:
    def __init__(self,cookie:str,jkId:int,lvAddress:str) -> None:
        self.cookie = cookie # type: str
        self.jkId = jkId # type: int
        self.lvAddress = lvAddress # type: str
        self.watchPageJson = "" # type: types.Any
    async def start(self):
        url = f"https://api.cas.nicovideo.jp/v1/services/live/programs/{self.lvAddress}"
        req = urllib.request.Request(url)
        liveCycle = ""
        with urllib.request.urlopen(req) as res:
            rawResponse = json.loads(str(res.read().decode("utf-8")))
            if rawResponse["meta"]["status"] != 200:
                raise Exception(f"{self.lvAddress} api data get error.")
            timeShift = rawResponse["data"]["timeshift"]
            liveCycle = rawResponse['data']['liveCycle'] # on_air , ended , before_open
        if liveCycle == "before_open":
            return
        self.watchPageJson = self._getWatchPage()
        if liveCycle == "ended":
            await self._getTimeShift(True)
        elif liveCycle == "on_air":
            await self._getTimeShift(False)

    async def _getTimeShift(self,saveTimeShiftLog:bool):
        broadcastId = self.watchPageJson["program"]["reliveProgramId"]
        audienceToken = self.watchPageJson["player"]["audienceToken"]
        frontendId = self.watchPageJson["site"]["frontendId"]
        webSocketUrl = self.watchPageJson["site"]["relive"]["webSocketUrl"]
        userId = self.watchPageJson["user"]["id"]
        channelId = self.watchPageJson["channel"]["id"] # ch1234
        status = self.watchPageJson["program"]["status"] # ENDED
        title = self.watchPageJson["program"]["title"]
        beginTime = datetime.datetime.fromtimestamp(int(self.watchPageJson["program"]["beginTime"]))
        endTime = datetime.datetime.fromtimestamp(int(self.watchPageJson["program"]["endTime"]))
        openTime = datetime.datetime.fromtimestamp(int(self.watchPageJson["program"]["openTime"]))
        scheduledEndTime = datetime.datetime.fromtimestamp(int(self.watchPageJson["program"]["scheduledEndTime"]))
        vposBaseTime = datetime.datetime.fromtimestamp(int(self.watchPageJson["program"]["vposBaseTime"]))
        視聴期限 = datetime.datetime.fromtimestamp(int(self.watchPageJson["programTimeshift"]["publication"]["expireTime"]))
        公開日時 = datetime.datetime.fromtimestamp(int(self.watchPageJson["programTimeshift"]["reservation"]["expireTime"]))
        #print(f"channelId        :{channelId}")
        #print(f"視聴期限         :{視聴期限:%Y/%m/%d %H:%M:%S}")
        #print(f"公開日時         :{公開日時:%Y/%m/%d %H:%M:%S}")
        #print(f"beginTime       :{beginTime:%Y/%m/%d %H:%M:%S}")
        #print(f"openTime        :{openTime:%Y/%m/%d %H:%M:%S}")
        #print(f"vposBaseTime    :{vposBaseTime:%Y/%m/%d %H:%M:%S}")
        #print(f"scheduledEndTime:{scheduledEndTime:%Y/%m/%d %H:%M:%S}")
        #print(f"endTime         :{endTime:%Y/%m/%d %H:%M:%S}")

        wssUrl = webSocketUrl
        threadId = ""
        async with websockets.connect(wssUrl) as i:
            a = {"type":"startWatching","data":{"stream":{"quality":"abr","protocol":"hls","latency":"low","chasePlay":False},"room":{"protocol":"webSocket","commentable":True},"reconnect":False}}
            await i.send(json.dumps(a))
            while True:
                a = json.loads(await i.recv())
                if a["type"] == "room":
                    threadId = a["data"]["threadId"]
                    break
        whenTimestamp = endTime + datetime.timedelta(seconds=30) # type: datetime.datetime
        if datetime.datetime.now() < whenTimestamp:
            whenTimestamp = datetime.datetime.now() + datetime.timedelta(seconds=30)
        chatObjList = []
        while True:
            async with websockets.connect("wss://msgd.live2.nicovideo.jp/websocket") as j:
                #print(f"request log until {whenTimestamp:%Y/%m/%d %H:%M:%S}")
                a = [
                        {"thread":{"thread":threadId,"version":"20061206","when":whenTimestamp.timestamp(),"user_id":userId,"res_from":-1000,"with_global":1,"scores":1,"nicoru":0,"waybackkey":""}},
                        {"ping":{"content":"pf:0"}},
                    ]
                await j.send(json.dumps(a))
                minDateObj = None # type: types.Optional[datetime.date]
                while True:
                    a = json.loads(await j.recv())
                    if "chat" in a:
                        dateObj = datetime.datetime.fromtimestamp(a["chat"]["date"])
                        if minDateObj == None or dateObj < minDateObj:
                            minDateObj = dateObj
                        chatObjList.append(a["chat"])
                    elif "ping" in a:
                        break
                if minDateObj == None:
                    #print(f"  get none break")
                    break
                #print(f"  get {len(chatObjList)} items")
                newWhenTimeStamp = minDateObj + datetime.timedelta(seconds=10)
                if newWhenTimeStamp == whenTimestamp:
                    #print(f"  all response get break.")
                    break
                whenTimestamp = newWhenTimeStamp
        if saveTimeShiftLog == True:
            logger.info(f"jk{self.jkId} {title} から {len(chatObjList)} 件のコメントを受信")
        else:
            logger.info(f"jk{self.jkId} {title} から {len(chatObjList)} 件のコメントを受信 (放送中)")
        DatabaseClass().saveXmlChat(self.jkId,self.lvAddress,chatObjList)
        if saveTimeShiftLog == True:
            DatabaseClass().saveTimeShiftLog(self.jkId,self.lvAddress,title)
    def _getWatchPage(self):
        url = f"https://live2.nicovideo.jp/watch/{self.lvAddress}"
        headers = {
            "Cookie": f"user_session={self.cookie}"
        }
        req = urllib.request.Request(url, None, headers)
        with urllib.request.urlopen(req) as res:
            rawResponse = str(res.read().decode("utf-8"))
            # JSON.parse(document.querySelector("#embedded-data").dataset.props)
            a = re.findall(r"<script id=\"embedded-data\" data-props=\"(.+?)\"></script>", rawResponse)
            if len(a) != 1:
                raise Exception()
            b = a[0]
            c = html.unescape(b)
            d = json.loads(c)
            return d
def getAllTimeshifts(jkId:int) -> typing.List[str]: # [ lv123456 , lv 987654]
    page = 1
    result = []
    while True:
        url = f"https://ch.nicovideo.jp/jk{jkId}/live?page={page}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as res:
            rawResponse = str(res.read().decode("utf-8"))
            #a = re.findall(r"<a href=\"https://live.nicovideo.jp/watch/(lv\d+)\" class=\"exclusion_btn_class\"", rawResponse)
            a = re.findall(r"<a href=\"https://live.nicovideo.jp/(?:watch|gate)/(lv\d+)\">", rawResponse)
            if len(a) == 0:
                break
            newUrl = 0
            for b in a:
                if b not in result:
                    result.append(b)
                    newUrl += 1
            if newUrl == 0:
                break
            page += 1
    return result
def jkIdToSqliteFileName(jkId:int) -> str:
    r = [i.sqliteFileName for i in channelDefs if i.jkNumber == jkId]
    if len(r) != 1:
        raise Exception(f"{jkId} not found")
    else:
        return r[0]

async def getTimeshift2(args):
    targetJkIds = [] # type: List[int]
    if args.station == None:
        targetJkIds = [i.jkNumber for i in channelDefs]
    else:
        targetJkIds = [i.jkNumber for i in channelDefs if i.cliName in args.station]
    for jkId in targetJkIds:
        downloadedLog = DatabaseClass().getSavedTimeShiftLogs(jkId) # 既に保存済みのリストを取得
        if args.allSave == True:
            # all downloadがtrueの場合は、保存済みリストを削除
            downloadedLog = [] # type: typing.List[TimeShiftLog]
        timeShiftThreas = getAllTimeshifts(jkId)
        for timeShiftThread in timeShiftThreas:
            logData = [i for i in downloadedLog if i.lvId == timeShiftThread]
            if 0 < len(logData):
                logger.info(f"{logData[0].title} ({logData[0].lvId}) はDL済みなのでスキップします")
                continue
            await DownloadTimeShift(args.cookie,jkId,timeShiftThread).start()

def getTimeshift(args):
    asyncio.run(getTimeshift2(args))

def getFromTsFile(args):
    for file in args.file:
        JkTxt(file,args.jkDir).getData()

def isFile(path:str) -> str:
    if os.path.isfile(path) == False:
        raise argparse.ArgumentTypeError("ファイルが存在しません")
    return path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='ニコニコ実況過去ログツール')
    subparsers = parser.add_subparsers()
    # 過去ログ取得
    parser_add = subparsers.add_parser('timeshift', help='ニコ生のタイムシフトから全チャンネルのログを取得する。プレミアムアカウント必須')
    parser_add.add_argument("-c","--cookie",action="store",type=str,required=True,help="cookieの値 user_session_123456_0123abcedf... の形式を想定")
    stationChoise = [i.cliName for i in channelDefs]
    parser_add.add_argument("-s","--station",action="append",type=str,choices=stationChoise,help="取得対象の局名 公式のチャンネルのみ対応。指定なしの場合は全局")
    parser_add.add_argument("-a","--allSave",action="store_true",help="既にDLしたタイムシフトも全て再取得します。個別のコメントに上書きはしないので、タイムシフトが何らかの理由でコメント数が増えた時に使う事を想定")
    parser_add.set_defaults(handler=getTimeshift)
    # tsファイル指定
    parser_add = subparsers.add_parser('ts', help='指定のtsファイルから自動的にコメントファイルを作成する。複数ファイル対応')
    parser_add.add_argument("file",action="store",type=isFile,nargs='+',help="tsファイルのパス 複数指定対応")
    parser_add.add_argument("-j","--jkDir",action="store",type=str,default="jk-txt",help="実況のtxtファイルを作成するディレクトリのパス。このパスの中にjk0 の局別フォルダを作り、その中に123456780.txt のテキストファイルを作成する")
    parser_add.set_defaults(handler=getFromTsFile)
    # サブコマンドここまで
    args = parser.parse_args()
    if hasattr(args, 'handler'):
        args.handler(args)
    else:
        # 未知のサブコマンドの場合はヘルプを表示
        parser.print_help()
