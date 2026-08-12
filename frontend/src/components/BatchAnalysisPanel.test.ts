import { describe, expect, it } from 'vitest';
import { parseUserId } from './BatchAnalysisPanel';

describe('parseUserId', () => {
  it.each([
    // 主页链接（带/不带协议）
    ['https://www.xiaohongshu.com/user/profile/5f0e9c2a1234', '5f0e9c2a1234'],
    ['www.xiaohongshu.com/user/profile/abcdef123', 'abcdef123'],
    ['xiaohongshu.com/user/profile/AbCdEf123', 'AbCdEf123'],
    // 裸 ID
    ['5f0e9c2a1234', '5f0e9c2a1234'],
    ['', ''],
    // 笔记链接/混合文本/无 ID 一律拒绝
    ['https://www.xiaohongshu.com/explore/xyz', ''],
    ['https://www.xiaohongshu.com/user/profile/', ''],
    ['abc https://x.com/user/profile/xyz', ''],
    ['abcdef 123', ''],
    ['https://www.xiaohongshu.com/user/profile/abc123?x=1', 'abc123'],
  ])('parse(%j) -> %j', (input, expected) => {
    expect(parseUserId(input)).toBe(expected);
  });
});
