import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from flask import Flask, request

import torch

from src.args import Args
from src.main import main
from src.models.model_builder import ExtSummarizer
from src.models.trainer_ext import build_trainer

hostname = "localhost"
port = 8080
app = Flask(__name__)

# model initialization
args = Args(
  test_from="src/bert_data/bertext_cnndm_transformer_cleaned.pt",
  text_src='',      # fill later
  report_rouge=False,
  use_bert_emb=True,
  use_interval=True,
  log_file="logs/ext_log_cnndm",
  load_from_extractive="EXT_CKPT"
)
model_flags = ['hidden_size', 'ff_size', 'heads', 'inter_layers', 'encoder', 'ff_actv', 'use_interval', 'rnn_size']
start = time.time()
checkpoint = torch.load(args.test_from, map_location=lambda storage, loc: storage)
print(f"Checkpoint loading time: {time.time() - start}s")
opt = vars(checkpoint['opt'])
for k in opt.keys():
  if (k in model_flags):
    setattr(args, k, opt[k])

device = "cpu" if args.visible_gpus == '-1' else "cuda"
device_id = 0 if device == "cuda" else -1

start = time.time()
model = ExtSummarizer(args, device, checkpoint)
print(f"Model instance time taken: {time.time() - start}s")
model.eval()

start = time.time()
trainer = build_trainer(args, device_id, model, None)
print(f"Time to build trainer: {time.time() - start}s")


@app.route("/", methods=['GET', 'POST'])
def index():
  if request.method == 'GET':
    return do_GET()
  elif request.method == 'POST':
    return do_POST(request.json)


def do_GET():
  sentences = [
    "But before I do that I have a question, you would want all tests from the three directories you linked above in the same `tests/selenium` directory? or you want them separated as they are now?",
    "so that the selenium directory is something like: ```\nselenium/base/\nselenium/notebook/\n``` Let me know if it's okay to start tackling the `notebook` directory and what structure do you prefer inside the new `tests/selenium` directory and I can start working on immediately.",
    "For now, let's keep the `tests/selenium` directory flat, placing files directly in there.",
    "We can easily rearrange it later if we need to divide them up, but I'm not convinced that the current way the JS tests are divided is that useful.Okay great!",
    "I'll start tackling the test files in the `tests/notebook` then, okay?Sounds good.",
    "@mpacer was looking at converting `markdown.js` from that folder, so if you want to start with another file, that would be good."
  ]

  args.text_src = ' [CLS] [SEP] '.join(sentences)

  data = {
    "summary": main(sentences, trainer, args),
    "status": 200
  }

  return data

def do_POST(body):
  
  if body['type'] == 'top-level':
    response = []
    for sentence_set in body['sentence_set']:
      sentences = []
      sentence_id_mapping = []
      for sentence in sentence_set['sentences']:
        sentences.append(sentence['text'])
        sentence_id_mapping.append((sentence['sentence_id'], sentence['text']))
      
      summary, sentence_ids = main(sentences, trainer, args)
      
      response_info_type = {
        'info_type': sentence_set['info_type'],
        'sentences': []
      }
      
      previous = 0
      for sentence_index in sentence_ids:
        response_info_type['sentences'].append({
          'id': sentence_id_mapping[sentence_index][0],
          'span': {
            'start': previous,
            'end': previous + len(sentence_id_mapping[sentence_index][1])
          }
        })
        
        previous += len(sentence_id_mapping[sentence_index][1]) + 1
      
      response.append(response_info_type)
    
    return {
      'summaries': response
    }
  elif body['type'] == 'comment-level':
    sentences = body['sentence_set']
    return {
      'summary': main(sentences, trainer, args)
    }


if __name__ == '__main__':
  app.run(host=hostname, port=port)