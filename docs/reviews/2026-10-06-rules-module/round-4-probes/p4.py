from common import *
for t in ["this afternoon","This Afternoon.","Thursday or Friday","Thursday, morning please","I don't mind","don't mind","dont mind","whenever","any time","anytime","any day","Thursday afternoon please",
          "morning or afternoon","either","either Thursday or Friday","Thursday and Friday mornings","thursday mornings","mornings","this Thursday","this morning","next Thursday","Thursday at 3pm","no preference","No preference.",
          "any time Thursday","I don't mind, any day", "tomorrow morning", "Thu", "thurs", "Tues", "Th", "sat", "Thursday or", "or", "the afternoon", "afternoons","in the morning","Thursday morning or Friday afternoon","not Monday","any morning","whatever works","no"]:
    w=parse_time_phrase(t); print(repr(t), w)
