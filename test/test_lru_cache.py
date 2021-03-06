# -*- coding: future_fstrings -*-
import os
import sys
import unittest

try:
  import unittest.mock as mock
except ImportError:
  import mock

from lru import LruCache
from lru.cache import (
  _create_node, _ExpNode, _Node,
  _CleanManager
)


def _get_printable(items):
  items = ', '.join(f"{k}: {v}" for k, v in items)
  return f'{{{items}}}'


class LruCacheTestCase(unittest.TestCase):
  def test_init(self):
    with self.assertRaises(ValueError):
      LruCache(capacity=0)
    pairs = [('a', 1), ('b', 2), ('c', 3), ('d', 4)]
    self.assertEqual(sorted(LruCache(pairs).items()), pairs)
    self.assertEqual(sorted(LruCache(dict(pairs)).items()), pairs)
    self.assertEqual(sorted(LruCache(**dict(pairs)).items()), pairs)
    self.assertEqual(sorted(LruCache(pairs, e=4, f=5, r=6).items()),
        pairs + [('e', 4), ('f', 5), ('r', 6)])
    cache = LruCache(pairs)
    cache.__init__([('e', 5), ('t', 6)])
    self.assertEqual(sorted(cache.items()), pairs + [('e', 5), ('t', 6)])

  def test_setitem(self):
    with self.assertRaises(ValueError):
      LruCache()['a'] = None
    with self.assertRaises(ValueError):
      LruCache()[None] = 'a'
    with self.assertRaises(ValueError):
      LruCache()[None] = None
    cache = LruCache(capacity=10)
    cache['a'] = 1
    cache['b'] = 2
    self.assertEqual(cache.items(), [('b', 2), ('a', 1)])
    cache['a'] = 3
    self.assertEqual(cache.items(), [('a', 3), ('b', 2)])
    cache['b'] = 4
    self.assertEqual(cache.items(), [('b', 4), ('a', 3)])
    cache['c'] = 5
    self.assertEqual(cache.items(), [('c', 5), ('b', 4), ('a', 3)])
    del cache['c']
    cache['c'] = 5
    self.assertEqual(cache.items(), [('c', 5), ('b', 4), ('a', 3)])

  def test_contains(self):
    self.assertFalse('a' in LruCache())
    self.assertFalse('a' in LruCache([('b', 2), ('c', 3), ('d', 4)]))
    self.assertTrue('b' in LruCache([('b', 2), ('c', 3), ('d', 4)]))
    self.assertTrue('b' not in LruCache())
    self.assertTrue('b' not in LruCache([('c', 3), ('d', 4)]))
    cache = LruCache([('b', 2), ('c', 3), ('d', 4)])
    self.assertTrue('a' not in cache)
    cache['a'] = 3
    self.assertTrue('a' in cache)

  def test_getitem(self):
    pairs = [('a', 1), ('b', 2), ('c', 3), ('d', 4)]
    cache = LruCache(pairs)
    with self.assertRaises(KeyError):
      LruCache()['key']
    with self.assertRaises(KeyError):
      cache['key']
    for key, value in pairs:
      self.assertEqual(value, cache[key])

  def test_delitem(self):
    with self.assertRaises(KeyError):
      del LruCache()['key']
    pairs = [('a', 1), ('b', 2), ('c', 3), ('d', 4)]
    cache = LruCache(pairs)
    with self.assertRaises(KeyError):
      del cache['key']
    for index, (key, value) in enumerate(pairs):
      del cache[key]
      self.assertEqual(cache.items(), pairs[index+1:][::-1])
    # start deleting from the tail
    cache.update(pairs)
    for index, (key, value) in enumerate(pairs[::-1]):
      del cache[key]
      index = len(pairs) - index - 1
      self.assertEqual(cache.items(), pairs[:index][::-1])

  def test_len(self):
    pairs = [('a', 1), ('b', 2), ('c', 3), ('d', 4)]
    cache = LruCache(pairs)
    self.assertEqual(len(pairs), len(cache))
    del cache['a']
    self.assertEqual(len(pairs) - 1, len(cache))
    cache.clear()
    self.assertEqual(len(cache), 0)

  def test_clear(self):
    pairs = [('a', 1), ('b', 2), ('c', 3), ('d', 4)]
    cache = LruCache(pairs)
    self.assertEqual(len(cache), len(pairs))
    cache.clear()
    self.assertEqual(len(cache), 0)
    cache.clear()
    self.assertEqual(len(cache), 0)
    cache.update(pairs)
    self.assertEqual(len(cache), len(pairs))
    cache.clear()
    self.assertEqual(len(cache), 0)

  def test_iter(self):
    pairs = [('a', 1), ('b', 2), ('c', 3), ('d', 4)]
    values = [value for key, value in pairs][::-1]
    cache = LruCache(pairs)
    self.assertEqual(list(iter(cache)), values)

  def test_copy(self):
    pairs = [('a', 1), ('b', 2), ('c', 3), ('d', 4)]
    cache = LruCache(pairs)
    self.assertEqual(cache.copy().items(), cache.items())
    self.assertEqual(cache.copy().keys(), cache.keys())
    self.assertEqual(LruCache().items(), LruCache().copy().items())
    self.assertEqual(LruCache().keys(), LruCache().copy().keys())

  def test_repr(self):
    pairs = [('a', 1), ('b', 2), ('c', 3), ('d', 4)]
    cache = LruCache(pairs)

    self.assertEqual(repr(cache), _get_printable(pairs[::-1]))
    self.assertEqual(repr(LruCache()), '{}')

  def test_eq(self):
    pairs = [('a', 1), ('b', 2), ('c', 3), ('d', 4)]
    cache = LruCache(pairs)
    self.assertTrue(cache == cache)
    self.assertTrue(LruCache() == LruCache())
    self.assertTrue(LruCache(pairs) == LruCache(pairs))
    self.assertFalse(LruCache() == list())
    self.assertFalse(LruCache(pairs) == LruCache(pairs[1:]))
    self.assertFalse(LruCache(pairs) == LruCache(pairs[::-1]))

  def test_create_node(self):
    node = _create_node(expires=10)
    self.assertIsInstance(node, _ExpNode)

    node = _create_node()
    self.assertIsInstance(node, _Node)

  @mock.patch('threading.RLock')
  @mock.patch('lru.cache._CleanManager')
  @mock.patch('lru.cache._create_node')
  def test_add(self, create_mock, CleanManagerMock, RLockMock):
    cleanManager = CleanManagerMock()
    lock = RLockMock()
    node = _ExpNode(key='a', value='b', expires=10)
    create_mock.return_value = node

    cache = LruCache()
    cache.add('a', 'b', expires=10)

    cleanManager.add.assert_called_with(node)
    lock.__enter__.assert_not_called()
    lock.__exit__.assert_not_called()

    cache.add('a', 'b', expires=10)

    cleanManager.add.assert_called()
    lock.__enter__.assert_called()
    lock.__exit__.assert_called()

  @mock.patch('threading.RLock')
  @mock.patch('lru.cache._CleanManager')
  @mock.patch('lru.cache._create_node')
  def test_delete(self, create_mock, CleanManagerMock, RLockMock):
    cleanManager = CleanManagerMock()
    lock = RLockMock()
    node = _ExpNode(key='a', value='b', expires=10)
    create_mock.return_value = node

    cache = LruCache()
    cache.add('a', 'b', expires=10)
    del cache['a']

    cleanManager.add.assert_called_with(node)
    cleanManager.on_delete.assert_called()
    lock.__enter__.assert_called()
    lock.__exit__.assert_called()

  @mock.patch('threading.RLock')
  def test_lock(self, RLockMock):
    lock = RLockMock()

    cache = LruCache()
    lock.__enter__.assert_not_called()
    lock.__exit__.assert_not_called()

    cache = LruCache(expires=10)
    lock.__enter__.assert_called()
    lock.__exit__.assert_called()


class CleanManagerTestCase(unittest.TestCase):
  @mock.patch('threading.Condition')
  @mock.patch('queue.PriorityQueue')
  @mock.patch('lru.cache._CacheCleaner')
  def setUp(self, CacheCleanerMock, QueueMock, ConditionMock):
    self.cleaner_mock = CacheCleanerMock()
    self.queue_mock = QueueMock()
    self.condition_mock = ConditionMock()
    self.cache_mock = cache = mock.MagicMock()
    self.clean_manager = _CleanManager(cache)

  def _assert_on_add(self, node):
    self.queue_mock.put.assert_called_once_with(node)
    self.condition_mock.__enter__.assert_called_once()
    self.condition_mock.__exit__.assert_called_once()
    self.condition_mock.notify.assert_called()

  @mock.patch('weakref.proxy')
  def test_add(self, proxy_mock):
    node = _ExpNode()
    proxy_mock.return_value = node

    self.clean_manager.add(node)
    self.cleaner_mock.start.assert_called_once()
    self._assert_on_add(node)

  @mock.patch('weakref.proxy')
  def test_add_when_initialized(self, proxy_mock):
    node = _ExpNode()
    proxy_mock.return_value = node

    self.clean_manager._initialized = True
    self.clean_manager.add(node)

    self.cleaner_mock.start.assert_not_called()
    self._assert_on_add(node)

  def test_delete(self):
    self.clean_manager.on_delete()
    self.condition_mock.__enter__.assert_called_once()
    self.condition_mock.__exit__.assert_called_once()
    self.condition_mock.notify.assert_called()


def main():
  unittest.main()

if __name__ == '__main__':
  main()
