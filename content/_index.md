+++
insert_anchor_links = "left"
title = "Home"
+++

{% crt() %}
```
     ->     />                                         
      \_____|                                          
      /\   /|                                          
  .--/, - / ,\--.  >(')____,  >(')____,  >(')____,  >(') ___,
  | <----o  | \ |    (` =~~/    (` =~~/    (` =~~/    (` =~~/
  \___/   - \___/      ---'~^~^~^`---'~^~^~^`---'~^~^~^`---'~^~^~
```
{% end %}

# Max Katz-Christy

Hello! Welcome to my website. I finally have one. I've made a number for other
people, and a few for myself a while ago. Maybe this is "the one". Maybe not.
We'll see in a few weeks.

My plan is to blog here. Hopefully the posts are interesting. We will see.
Maybe this will inspire me to do more projects. Maybe it will scare me away
because then I have to write about them.

For now, check out my [first big post!](/blog/mapping-tgtg/)

## Tech Stack

### Hardware

This website is hosted from a Lenovo Thinkpad T480 sitting on top of my mom's
desktop in Boston. Sometimes I gotta ask my mom to give my server a kick for me
to get it up and running.

### Containerization

[Docker](https://www.docker.com/)! Deployed via [OpenTofu](https://opentofu.org/)

See my [repo here for more](https://github.com/maxtkc/home-docker)

### Git Hosting/CI/CD

I use [Forgejo](https://forgejo.org/)! I really like it. I host my own Forgejo
instance [here](https://git.kcfam.us/).

It uses the docker based runners so it compiles and deploys via a docker volume
much faster than github. It's not even a custom runner... It installs zola and
then deploys the site.

### Static Site Generation

I use [Zola](https://www.getzola.org/) with the
[Duckquill](https://duckquill.daudix.one/) theme.

### Why?

I dunno, it's pretty cool to run entirely my own stuff though!
