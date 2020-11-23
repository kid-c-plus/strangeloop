#!/usr/local/bin/python3

import unittest

from app import flaskapp, db, models, views
import requests as req
import re

from pydub import AudioSegment, playback
from io import BytesIO

BASEURL = "http://localhost:5000/"
NICKNAME = "rick's cool pedal"
MAN_ENDPOINTS = [("newsession", views.NONE_RETURN), ("endsession", views.FAILURE_RETURN), ("joinsession", views.FAILURE_RETURN), ("leavesession", views.FAILURE_RETURN)]

def genmac(index):
    return re.sub("(..)", r"\1:", ("0" * 12 + str(index))[-12:])[:-1]

def genpedal(index=0, nickname=NICKNAME):
    return {'mac' : genmac(index), 'nickname' : nickname}

class TestCase(unittest.TestCase):
    def setUp(self):
        flaskapp.config['TESTING'] = True
    
    def tearDown(self):
        meta = db.metadata
        for table in reversed(meta.sorted_tables):
            db.session.execute(table.delete())
        db.session.commit()

    def testnewsession(self):
        u = req.post(BASEURL + "newsession", data = genpedal()).text
        gs = req.post(BASEURL + "getsession", data = genpedal()).text
        assert gs == "owner:%s" % u

    def testmanysessions(self):
        for i in range(200):
            u = req.post(BASEURL + "newsession", data=genpedal(index=i)).text
        assert req.post(BASEURL + "newsession", data=genpedal(index=200)).text == views.FULL_RETURN
    
    def testmultisession(self):
        req.post(BASEURL + "newsession", data=genpedal())
        u = req.post(BASEURL + "newsession", data=genpedal()).text
        assert u == views.NONE_RETURN

    def testjoinsession(self):
        pedal1 = genpedal()
        sess = req.post(BASEURL + "newsession", data=pedal1).text
        pedal1['sessionid'] = sess
        assert req.post(BASEURL + "joinsession", data=pedal1).text == views.FAILURE_RETURN

        pedal2 = genpedal(1)
        pedal2['sessionid'] = sess
        assert req.post(BASEURL + "joinsession", data=pedal2).text == views.SUCCESS_RETURN

    def testfullsession(self):
        sess = req.post(BASEURL + "newsession", data=genpedal()).text
        for i in range(1, 21):
            pedal = genpedal(i)
            pedal['sessionid'] = sess
            req.post(BASEURL + "joinsession", data=pedal)
            if i == 20:
                assert req.post(BASEURL + "joinsession", data=pedal).text == views.FULL_RETURN

    def testendsession(self):
        pedal1 = genpedal()
        sess = req.post(BASEURL + "newsession", data=pedal1).text

        pedal2 = genpedal(1)
        pedal2['sessionid'] = sess
        req.post(BASEURL + "joinsession", data=pedal2)

        assert req.post(BASEURL + "endsession", data=pedal2).text == views.FAILURE_RETURN
        assert req.post(BASEURL + "endsession", data=pedal1).text == views.SUCCESS_RETURN
        assert req.post(BASEURL + "joinsession", data=pedal2).text == views.FAILURE_RETURN 

    def testleavesession(self):
        pedal1 = genpedal()
        pedal2 = genpedal(1)
        pedal3 = genpedal(2)

        sess = req.post(BASEURL + "newsession", data=pedal1).text
        pedal2['sessionid'] = sess 
        pedal3['sessionid'] = sess 

        req.post(BASEURL + "joinsession", data=pedal2)
        req.post(BASEURL + "joinsession", data=pedal3)

        assert req.post(BASEURL + "leavesession", data=pedal1).text == views.SUCCESS_RETURN
        pedal1['sessionid'] = sess
        assert req.post(BASEURL + "joinsession", data=pedal1).text == views.SUCCESS_RETURN
        req.post(BASEURL + "leavesession", data=pedal1)
        assert req.post(BASEURL + "leavesession", data=pedal2).text == views.SUCCESS_RETURN
        assert req.post(BASEURL + "leavesession", data=pedal3).text == views.SUCCESS_RETURN
        assert req.post(BASEURL + "joinsession", data=pedal2).text == views.FAILURE_RETURN
       
    def testincompletes(self):
        for endpoint, expect in MAN_ENDPOINTS:
            assert req.post(BASEURL + endpoint, data={}).text == expect
            assert req.post(BASEURL + endpoint, data={'mac' : genmac(1)}).text == expect
            assert req.post(BASEURL + endpoint, data={'nickname' : NICKNAME}).text == expect

    def testmemberlist(self):
        nicknames = ["rick", "ash", "ma,tt"]
        sess = req.post(BASEURL + "newsession", data=genpedal(0, nicknames[0])).text
        pedals = [genpedal(0, nicknames[0])]

        for i in range(1, len(nicknames)):
            pedal = genpedal(i, nicknames[i])
            pedal['sessionid'] = sess
            pedals.append(pedal)
            req.post(BASEURL + "joinsession", data=pedal)
        
        assert req.post(BASEURL + "getmembers", data=pedals[0]).text != ",".join(nicknames)
        assert req.post(BASEURL + "getmembers", data=pedals[0]).text == ",".join([name.replace(",", "") for name in nicknames])
        req.post(BASEURL + "leavesession", data=pedals[2])
        nicknames.pop(2)
        assert req.post(BASEURL + "getmembers", data=pedals[0]).text == ",".join([name.replace(",", "") for name in nicknames])

    def testaddtracks(self):
        nicknames = ["rick", "ash", "matt"]
        sess = req.post(BASEURL + "newsession", data=genpedal(0, nicknames[0])).text
        pedals = []

        refloop = None
        for i in range(len(nicknames)):
            pedal = genpedal(i, nicknames[i])
            pedal['sessionid'] = sess
            pedal['index'] = i
            pedals.append(pedal)
            if i:
                req.post(BASEURL + "joinsession", data=pedal)
            with open("test_tones/%d" % i, mode="rb") as wavfile:
                wavdata = wavfile.read()
            wav = AudioSegment(data=wavdata, **models.PYDUB_ARGS)
            if refloop:
                refloop = refloop.overlay(wav)
            else:
                refloop = wav
            assert req.post(BASEURL + "addtrack", data=pedals[i], files={'wavdata' : BytesIO(wavdata)}).text == views.SUCCESS_RETURN

        resploop = req.post(BASEURL + "getcomposite", data=pedals[0]).content
        '''
        print("playing response...")
        playback.play(AudioSegment(data=resploop, **models.PYDUB_ARGS))
        print(len(resploop))
        print("playing reference...")
        playback.play(refloop)
        print(len(refloop.raw_data))
        '''
        assert resploop == refloop.raw_data

    def testmanytracks(self):
        pedal = genpedal()
        req.post(BASEURL + "newsession", data=pedal)
        wav = AudioSegment.from_wav("test_tones/0.wav").raw_data
        for i in range(30):
            pedal['index'] = i
            req.post(BASEURL + "addtrack", data=pedal, files={'wavdata' :  BytesIO(wav)})
        pedal['index'] = 30
        assert req.post(BASEURL + "addtrack", data=pedal, files={'wavdata' :  BytesIO(wav)}).text == views.FULL_RETURN

    def testremovetracks(self):
        nicknames = ["rick", "ash", "matt"]
        sess = req.post(BASEURL + "newsession", data=genpedal(0, nicknames[0])).text
        pedals = []

        refloop = None
        for i in range(len(nicknames)):
            pedal = genpedal(i, nicknames[i])
            pedal['sessionid'] = sess
            pedal['index'] = i
            pedals.append(pedal)
            if i:
                req.post(BASEURL + "joinsession", data=pedal)
            with open("test_tones/%d" % i, mode="rb") as wavfile:
                wavdata = wavfile.read()
            wav = AudioSegment(data=wavdata, **models.PYDUB_ARGS)
            if i != 2:
                if refloop:
                    refloop = refloop.overlay(wav)
                else:
                    refloop = wav
            assert req.post(BASEURL + "addtrack", data=pedals[i], files={'wavdata' : BytesIO(wavdata)}).text == views.SUCCESS_RETURN

        assert req.post(BASEURL + "getcomposite", data=pedals[0]).content != refloop.raw_data

        assert req.post(BASEURL + "removetrack", data={'mac' : pedals[0]['mac'], 'index' : 2}).text == views.FAILURE_RETURN
        assert req.post(BASEURL + "removetrack", data={'mac' : pedals[1]['mac'], 'index' : 2}).text == views.FAILURE_RETURN
        assert req.post(BASEURL + "removetrack", data={'mac' : pedals[2]['mac'], 'index' : 2}).text == views.SUCCESS_RETURN

        resploop = req.post(BASEURL + "getcomposite", data=pedals[0]).content

        '''
        print("playing response...")
        playback.play(AudioSegment(data=resploop, **models.PYDUB_ARGS))
        print(len(resploop))
        print("playing reference...")
        playback.play(refloop)
        print(len(refloop.raw_data))
        '''
        assert resploop == refloop.raw_data
                
if __name__ == "__main__":
    unittest.main()
