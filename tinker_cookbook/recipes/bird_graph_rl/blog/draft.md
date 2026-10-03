# We trained a small model to query a graph with RL. It learned something different from what we expected.

*Draft 1, 3 October 2026. Not for publication yet; open items are listed at the end.*

Most reinforcement-learning write-ups end with a curve going up and to the right. Ours has one of
those too. But the more useful thing we learned came from the place where the curve did not go
up, and from a prediction we wrote down in advance and then watched fail. This post tells both
halves.

## The problem

Suppose you have a graph database and you want people to be able to ask it questions in plain
English. The standard answer is an agent: a language model that can write a query, run it, look
at what came back, and try again until it has an answer. Large models do this reasonably well.
Small models, the kind you can afford to run at volume, do it noticeably worse.

We wanted to know how much of that difference can be trained away. Not by collecting thousands
of hand-written examples, which nobody has for their own database, but by letting the model
practise against the database itself and rewarding it when its final query returns the right
rows.

## The setup, briefly

Our graph is one of the databases from the BIRD text-to-SQL benchmark, a dump of a statistics
Q&A site, remodelled as a property graph in Neo4j: about 650,000 nodes and 1.38 million
relationships, covering users, questions, answers, comments, votes, tags, badges and edit
history.

The agent is Qwen3.5-9B with a single tool that runs a read-only Cypher query. It gets a
question, sometimes with a hint, and has up to eight turns. Whatever its last successful query
returns is its answer.

We score answers two ways, and the distinction turns out to matter a great deal. *Strict*
accuracy asks whether the rows the agent returned are exactly the reference rows. *Lenient*
accuracy only asks whether the right values are in there, forgiving an extra column or a
different column order. An agent that answers "how many posts did this user write?" with the
user's id and the number 121 is leniently right and strictly wrong.

For training we used no human questions at all. We generated queries first, by enumerating
query shapes over the schema, filling in real values and executing them, and then had a model
write a natural question for each one. Some query shapes were held out completely, so that we
could later ask whether the agent had learned to query the graph or merely memorised patterns.

The reward is as plain as we could make it. Run the agent's final query, compare its rows with
the reference rows, and score the overlap:

$$ r = \frac{2PR}{P + R} $$

where $P$ is the fraction of the agent's rows that are correct and $R$ the fraction of the
reference rows it found. The reward is 1 exactly when the answer is strictly right. There is no
judge model anywhere in the loop. Each training step takes 8 questions, lets the model attempt
each one 8 times, and nudges it towards the attempts that scored above the average for that
question. A run is 37 such steps: about 2,400 attempts, under an hour, roughly $37 including
all the evaluation afterwards.

The test that matters is the benchmark's own 186 human-written questions for this database,
which the model never sees in training. Because the model samples its answers, any single pass
over 186 questions is noisy, so we run every question four times and compare models question by
question.

## What went up

On generated questions the model had not seen, training worked, and by a wide margin.

![Accuracy on held-out generated questions](figures/fig2_generated_heldout.png)

On new questions built from query shapes it had practised, strict accuracy went from 0.50 to
0.68. On query shapes it had never encountered in training, it went from 0.29 to 0.45. That
second number is the one we care about: the model was not shown these patterns and still got
half again as many right.

It helps to see what that looks like. Here is a four-hop question from the unseen set:

> What mean score do the distinct posts commented on by authors of posts linked to from posts
> titled 'Local median and local average' have?

The untrained model spends all eight turns on it. It follows the link relationship in the wrong
direction, writes three queries that do not parse, and runs out of turns without an answer. The
trained model writes one query, gets 4.0, and stops. There are forty questions in that set
where the untrained model is wrong by any standard and the trained one is exactly right.

On the human-written questions the picture is more modest but real. Strict accuracy rose from
0.421 to 0.466 in our first run and 0.476 in our second. A model three times the size, Qwen3.8-27B,
scores 0.608 untrained, so a 9B model closed between a quarter and a third of the gap to a 27B
one with an hour of training.

Before training anything we had fixed what would count as a result: the improvement had to be
statistically distinguishable from zero and at least five points. The first run came in at +4.6
points and missed that bar by less than half a point. The second came in at +5.5 and cleared
it. We do not think the second run is better than the first; the two are within noise of each
other. The fair summary is that RL bought about five points on human questions, twice.

## What did not go up

Here is the same result, scored leniently.

![Accuracy on the 186 human-written questions](figures/fig1_human_questions.png)

Lenient accuracy on human questions did not move. It was 0.574 before training, 0.577 after the
first run and 0.552 after the second. The model is not finding more right answers to human
questions. It is returning the answers it already had in the form that was asked for.

Sorting every one of the 744 attempts by how it ended makes this visible:

![Outcome of each attempt](figures/fig3_outcomes.png)

Between the untrained model and the first run, the light-green band, right values in the wrong
shape, shrinks by 32 attempts and the dark-green band grows by 34. That is nearly the whole
gain. The untrained model liked to return a little extra: an id next to a name, a title next to
a count. Training taught it to stop.

That is a genuine improvement, and for anyone whose downstream code expects a particular shape
it is the improvement that matters. But it is not the one we set out to get, and it raised an
obvious question. On generated questions, lenient accuracy rose by nine to twelve points. The
model did learn to find more right answers there. Why did that part stay behind?

## A guess, written down first

Our first suspect was the kind of question we had trained on. We measured it: across 6,601
human-written questions from 69 other databases in the same benchmark, more than half are plain
lookups and another quarter are "how many". Sums, averages, minima and maxima are about 12%. In
our training set they were nearly half.

![Question types: human-written versus our two training sets](figures/fig4_question_mix.png)

It was a tidy story. We had trained the model on a diet that did not resemble what people ask.

Tidy stories are dangerous, so before building anything we wrote the prediction into the
experiment journal: a training set whose mix follows the human one will raise lenient accuracy
on human questions above the first run. We said which checkpoint we would evaluate, which
comparison would decide it, and what we would do next in each case. Then we built the new set,
320 questions matched to the human mix, had a second agent verify independently that none of it
leaked into any held-out set, and trained again with everything else unchanged.

The prediction failed. Lenient accuracy in the second run was 2.4 points *below* the first, with
an interval that just includes zero. Looking at where attempts went, the near-misses mostly
turned into plain misses rather than hits. Matching the kinds of questions people ask did not
make the model better at answering people.

We would rather report that than not. It is one run against one run, so we cannot say the
question mix is irrelevant, only that it is not the explanation we thought it was.

## Where we think the gap is

While the second run was training, and before its result existed, the agent checking our data
noticed something about the hints. In the benchmark, a hint explains a phrase from the question:
"elder users refers to Age > 65". In our generated data, 82% of hints explain a term that never
appears in the question at all, because the generator described what its query used rather than
what the question asked. Among human-written hints that figure is 2.2%.

A model rewarded for exact answers while being handed hints about fields it must not return has
a good reason to learn to ignore hints, and on the human questions the hints are the useful
kind. That is our current best guess. It is only a guess. Neither run can test it, because both
share the flaw.

## What we would tell someone starting this

Reward from execution works, and it is cheap. No judge, no demonstrations, one hour, tens of
dollars, and a small model gets measurably better at using a tool against a real database,
including on query shapes it has not seen.

Score your results in more than one way. If we had only reported strict accuracy we would have
a clean five-point win and a wrong idea of what the model learned.

Write the prediction down before the run. Ours was wrong, and because it was written down we
know it was wrong, rather than having a story that quietly rearranged itself around the result.

And look hard at synthetic data for the ways it is unlike the real thing. We checked the
obvious property, the kinds of questions, and missed a less obvious one.

## A note on how this was done

The work was carried out by three AI agents with a human directing: one ran training and
evaluation, one independently recomputed every headline number from the raw outputs with its own
code, and one generated data against a written specification. They shared a single append-only
ledger of facts. Several statements in this post are different from their first drafts because
the checking agent would not accept them, including our first reading of the second run.

---

### Sources for the numbers

All figures are produced by `make_figures.py` from the run folders; the values plotted are in
`figures/numbers.json`. Intervals quoted below are 95% paired bootstrap intervals over questions.

| claim | value | ledger |
|---|---|---|
| human questions, strict: untrained / run 1 / run 2 | 0.4207 / 0.4664 / 0.4758 | T8 |
| human questions, lenient | 0.5739 / 0.5766 / 0.5524 | T8 |
| run 1 − untrained, strict | +0.0457 [+0.0094, +0.0833] | T8, T10 |
| run 2 − untrained, strict | +0.0551 [+0.0202, +0.0914] | T8 |
| run 2 − run 1, strict / lenient | +0.0094 [−0.0188, +0.0376] / −0.0242 [−0.0538, +0.0040] | T8 |
| outcome counts per 744 attempts | 313/114/192/125, 347/82/213/102, 354/57/224/108 (+1 no query) | T12 |
| seen structures, strict | 0.5038 / 0.6780 / 0.6667 | T9 |
| unseen structures, strict | 0.2944 / 0.4472 / 0.4056 | T9 |
| Qwen3.8-27B untrained, strict | 0.608 (one sample) | run folder `e2_full_qwen3_8_27b` |
| hints explaining an absent term | 82.1% ours, 2.2% human | W11 |
| question mix | see figure 4 | `numbers.json`, W9 |
| cost of a run with evaluations | $37.25 billed | T11 |

### Open before publishing
- The training objective is described in words; the exact formula should be quoted from the
  official Tinker documentation, not written from memory.
- Two or three more worked examples, with the rule for choosing them stated.
- The hint experiment, if it is run, would change the ending.
- This post covers the Qwen3.5-9B runs on Tinker only. The same recipe applied to a larger model
  on Fireworks is written up separately; link it here once it exists.
