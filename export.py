import torch
import torch.nn as nn
import json

class ParametricAmpModel(nn.Module):
    def __init__(self, hidden_size=64):
        super().__init__()
        self.lstm = nn.LSTM(input_size=2, hidden_size=hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

model = ParametricAmpModel(hidden_size=64)
model.load_state_dict(torch.load("sansamp_model.pth", map_location="cpu"))

# Przerabiamy tensory na zwykły tekst dla C++
json_dict = {key: tensor.numpy().tolist() for key, tensor in model.state_dict().items()}

with open("sansamp_weights.json", "w") as f:
    json.dump(json_dict, f, indent=4)

print("Gotowe! Wyeksportowano wagi do pliku: sansamp_weights.json")