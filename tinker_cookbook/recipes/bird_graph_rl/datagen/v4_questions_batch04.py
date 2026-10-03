"""Individually written questions, frozen after rendered-text review."""
from .v4_question_authoring import append_batch

q=[
'What is the minimum reputation among the authors of posts linked to from posts with revision activity by users who joined on 2012-03-05?',
"What average score do the posts commented on by authors of posts linked to from posts titled 'Understanding Odds Ratios in Logistic Regression' with a recorded title have?",
"For the posts commented on by authors of posts linked to from posts titled 'Probability of all family members having birth week in series according to their age' with a recorded title, give the mean score.",
"How high is the average score of the posts commented on by authors of posts linked to from posts titled 'How to estimate the parameters of a Gaussian distribution sample with outliers?' with a recorded title?",
'Among the questions to which answers created on 2012-02-28 respond, which question ranks 3 by descending score? Return its score and title or first 120 body characters when untitled.',
'Among the tags with stored usage count between 116 and 117 inclusive, show the tag ranked 3 by descending stored usage count. Give its name and count.',
'What tag occupies rank 3 in the tags with stored usage count between 267 and 369 inclusive when sorted from highest to lowest stored usage count? Include the tag name and count.',
"What is the total reputation of the different authors of accepted answers to questions titled 'What to do with confounding variables?' with no recorded location?",
"Add up the reputation of the authors of posts linked to from posts titled 'In simple linear regression, why the covariance between y bar and beta1 hat is zero?' with no recorded location, once per distinct author.",
"What combined score comes from the posts authored by the user 'ulidtko', counting each post once?",
'For the authors of questions answered by the user with ID 16004, calculate total reputation, once per distinct author.',
'How much reputation do the authors of posts linked to from posts commented on by the user with ID 43304 have altogether? Count each author once.',
'Give the combined reputation of the distinct authors of posts linked to from posts commented on by the user with ID 12885.',
'Add the reputation of the authors of posts linked to from posts commented on by the user with ID 8207 without counting any author twice.',
"What is the sum of the stored usage counts of the distinct tags on posts with revision activity by the user 'Lerong'?",
"For each different tag in the tags on posts with revision activity by the user 'andrecb', take its stored usage count and add those counts. What total results?",
'What is the total reputation of the users with reputation between 101 and 121 inclusive?',
"Who are the 5 highest-reputation users among the authors of posts linked to from posts commented on by the user 'varty'? Return display names and reputation, highest first.",
'List up to 10 of the authors of accepted answers to questions created on 2012-02-14 with the greatest reputation, showing display names and reputation in descending order.',
"Among the posts authored by holders of the 'Precognitive' badge, which 10 score highest? Show scores with titles or first-120-character body excerpts, highest score first.",
]
append_batch(300,q)
