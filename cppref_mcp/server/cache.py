from collections import OrderedDict
from typing import Optional


class LRUCache:
  def __init__(self, capacity: int):
    self.cache = OrderedDict()
    self.capacity = capacity

  def get(self, key: str) -> Optional[str]:
    if key not in self.cache:
      return None
    self.cache.move_to_end(key)
    return self.cache[key]

  def put(self, key: str, value: str):
    if key in self.cache:
      self.cache.move_to_end(key)
    self.cache[key] = value
    if len(self.cache) > self.capacity:
      self.cache.popitem(last=False)
