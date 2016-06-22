
## To do analysis of build failures

Install

```
pyp install -r requirements.txt
```

It is a two step process:

1. Do the analysis

```
python evg_analyzer.py
```

2. View the analysis

```
python www\runserver.py
```
The webserver is running at <http://localhost:5555/>

## Other Useful Scripts

*Scripts to deduplicate stacks from hang_analyzer.py*

```
python win_deadlock_analyzer.py
python gdb_deadlock_analyzer.py
```
