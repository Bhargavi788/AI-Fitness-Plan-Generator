# Test Cases

| Test Input | Expected Output | Actual Output | Pass/Fail |
|---|---|---|---|
| Beginner, no equipment, 3 days, fat loss | Plan generated using only bodyweight exercises; 3 workout days with rest days; diet plan emphasizes deficit; saved to DB | | |
| Intermediate, dumbbells only, 4 days, muscle building | Plan uses dumbbell exercises and beginner/intermediate difficulty only; 4 workouts; diet plan recommends surplus & protein; saved | | |
| Advanced, full gym, 5 days, general fitness | Plan can include barbell, machine, advanced exercises; 5 workouts; balanced diet; saved | | |
| Beginner, resistance band, 3 days, flexibility | Plan uses resistance band and bodyweight exercises; focuses mobility and flexibility; saved | | |

## Verification checks
- Exercises used in plans must exist in `exercises.json`.
- Beginners must not receive Advanced exercises.
- Exercises must match user's selected equipment.
- GEMINI key missing should fallback to local generator and show info message.
- Invalid inputs should produce friendly flash messages.

*** Usage notes ***
Run the app, initialize DB via `/init-db`, register test users, and run the dashboard flows for each test profile. Fill Actual Output and Pass/Fail after manual verification.
