-- ============================================================
--  易淘商城 · 初始化数据
--  依赖：先执行 sql/schema.sql 建库建表
--
--  这些数据是「测试靶场」的固定起点，每次重置都回到这个状态。
--  库存刻意压得很小（3 / 5 / 8），方便观察边界值与并发争抢。
-- ============================================================

USE easybuy_mall;

-- 清空所有表。
-- 这里用 DELETE 而不是 TRUNCATE：TRUNCATE 是 DDL，在 InnoDB 上要重建表，
-- 而测试用例之间要反复重置数据，用 TRUNCATE 会让整轮测试慢十倍。
-- 表都很小，DELETE 更快。
-- （代价：自增 ID 不会归零。测试用例不依赖固定 ID，所以无所谓。）
SET FOREIGN_KEY_CHECKS = 0;
DELETE FROM stock_logs;
DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM carts;
DELETE FROM sessions;
DELETE FROM products;
DELETE FROM users;
SET FOREIGN_KEY_CHECKS = 1;
-- ------------------------------------------------------------
-- 用户
--   user_a / user_b 是留给「越权测试」的两个账号：
--   用 A 的 token 去访问 B 的订单，看能不能访问到。
-- ------------------------------------------------------------
INSERT INTO users (id, username, password, phone) VALUES
    (1, 'user_a', '123456', '13800000001'),
    (2, 'user_b', '123456', '13800000002'),
    (3, 'demo',   '123456', '13800000003');

-- ------------------------------------------------------------
-- 商品（6 件，覆盖多个分类）
-- ------------------------------------------------------------
INSERT INTO products (id, name, category, price, stock, status, description) VALUES
    (1, '无线蓝牙耳机',        '数码',   199.00, 50,  'ON_SALE', '主动降噪，续航 30 小时'),
    (2, '机械键盘 87键',       '数码',   329.50,  8,  'ON_SALE', '红轴，全键无冲'),
    (3, '移动电源 20000mAh',   '数码',   129.00,  3,  'ON_SALE', '双向快充，可上飞机'),
    (4, '纯棉短袖T恤',         '服饰',    59.90, 100, 'ON_SALE', '精梳棉，不起球'),
    (5, '经典帆布鞋',          '服饰',   189.00, 20,  'ON_SALE', '硫化工艺，耐磨大底'),
    (6, '每日坚果礼盒 750g',   '食品',    99.99,  5,  'ON_SALE', '30 小包，独立分装');

-- ------------------------------------------------------------
-- 库存流水：补一条期初入库，让「库存 = 流水合计」这个等式成立
--   测试时可以用它做反向核对：
--     SELECT stock FROM products WHERE id = 3;
--     SELECT SUM(change_qty) FROM stock_logs WHERE product_id = 3;
--   两个值应该永远相等。如果取消订单重复回滚库存，这里就会对不上。
-- ------------------------------------------------------------
INSERT INTO stock_logs (product_id, change_qty, reason) VALUES
    (1, 50,  'INIT'),
    (2,  8,  'INIT'),
    (3,  3,  'INIT'),
    (4, 100, 'INIT'),
    (5, 20,  'INIT'),
    (6,  5,  'INIT');
