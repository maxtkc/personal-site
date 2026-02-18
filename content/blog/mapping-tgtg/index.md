+++
authors = ["Max Katz-Christy"]
title = "Mapping My Leftover Food Tourism"
description = "How to turn eating into a casino game"
date = 2025-02-18
# updated = "2025-02-18"
[taxonomies]
tags = ["TGTG", "Reverse Engineering"]
[extra]
banner = "banner.webp"
toc = true
toc_inline = true
toc_ordered = true
# trigger = "This page contains blackjack and hookers, and bad jokes such as this one."
disclaimer = """
- The Too Good to Go API is not meant for this use
- Whoopsies
"""
[extra.comments]
# Long thread with image
#
# host = "mastodon.social"
# user = "brownpau"
# id = "104529877688537579"
#
# Thread with multiple images per post
#
# host = "mastodon.blaede.family"
# user = "cassidy"
# id = "112774854109302186"
#
# Thread with preview cards
# host = "mastodon.blaede.family"
# user = "cassidy"
# id = "110669429936617026"
#
# Post on GoToSocial
#
# host = "alpha.polymaths.social"
# user = "orbitalmartian"
# id = "01J7ETKJ19FGBDQGS1ZWZ3KEPP"
#
# Post on Sharkey
#
# host = "is-a.wyvern.rip"
# user = "volpeon"
# id = "9qy755nsnu2c0hbc"
host = "better.boston"
user = "maxtkc"
id = "tbd"
+++
# Mapping My Leftover Food Tourism

## An Addict

Gambling is very addictive. I have an addictive personality. I have spent $TBD in an online casino where the only possible reward is food. This addiction has caused me to run, bike, and train for miles towards pickup locations in a variety of far flung places all over the US and Europe.

Maybe this is an unfair comparison because the house and I both usually win. While I'm not a huge fan of most big companies, Too Good To Go is one of my favorites. They host a platform where restaurants can post "surprise bags" for around a third of the original price that can be picked up in limited numbers at given times. If it was just for the food alone, I don't know if I would be winning. I spend lots of time and energy collecting the food. I don't know if there's any hunter/gatherer left in our DNA, but I do get quite a bit of pleasure from scouting out what is available and making a collection. Additionally, while solo traveling, it gives me a sense of purpose and gives me an excuse to explore the city in ways that not many others do. And of course, the off chance encounters with other too good to goers is quite interesting.

## The Problem

The stats in the Too Good To Go app are pretty limited.

Pic app

I mean, who cares about climate change anyways. Why can't I export the data, or see a map of places I've been? I have so many more important things to do, but this is bugging me.

## Existing "Research"

There's a Too Good To Go python package that I've used before, let's see if that works.

Pic

Nope, auth issues. Let's try this package.

Pic

Wheee! But wait, they don't have the history API written in? I guess people just don't care...

## Reverse Engineering

Too Good to Go's API is not documented anywhere or intended for public use outside of the app. However, my app is able to look at my past pickups. So I can be sure that it's possible, if my computer does the exact same thing as my phone, their server will provide me with my too good to go history.

Because Apple and Google are both shitty big companies, they don't want you to be able to figure out what is running on your phone. However, there's only so much they can do, because the requests to the server for data must leave the phone and fly on their own. They are usually encrypted after leaving the phone, with that tricky little s on the end of http.

So, how do we jump in the middle of this? We can instruct the phone to use a proxy! A proxy, as the name implies, sends requests to servers on behalf of the original sender. So, I boot up a very simple proxy on my laptop and point my phone to it. 

Http requests work! Ok, now what about a secure request? Certificate not valid? When I send an https request, an app on my phone first sets up a secure connection with some fancy math. My phone has a list of "System Certificate Authorities" that it allows. Websites go to one of these authorities to get approved, proving that they are actually "phoey.com" or whatever. Once the authority is convinces of who they are, they are given a signed key. They can provide this key when people make requests to them, and, if the user trusts their signing authority, can trust that they are who they say they are.

Think of it like countries giving out passports. I go to the US and say, I'd like a passport. First, they make sure I am who I am. Then I can go around to any place in the world that trusts the US passport authority and they can be certain I am who I say I am.

Now, what my proxy is trying to do is, whenever I make any request, respond with, "Yes, I am phoey.com!" If my phone trusts it and sends the request, my proxy will get the request and then resend it on my behalf
