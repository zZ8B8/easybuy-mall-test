-- ============================================================
--  易淘商城 · 数据库结构
--  MySQL 8.0+ / utf8mb4 / InnoDB
--
--  执行方式（任选其一）：
--    1) 双击项目根目录的「一键启动.bat」，会自动执行本文件
--    2) 命令行： mysql -u root -p < sql/schema.sql
--    3) Navicat：新建查询，把本文件内容粘进去执行
-- ============================================================

CREATE DATABASE IF NOT EXISTS easybuy_mall
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE easybuy_mall;

-- 先删后建，保证每次执行都是干净结构（顺序：先子表后父表）
DROP TABLE IF EXISTS stock_logs;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS carts;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS users;


-- ------------------------------------------------------------
-- 用户表
-- ------------------------------------------------------------
CREATE TABLE users (
    id          INT           NOT NULL AUTO_INCREMENT COMMENT '用户ID',
    username    VARCHAR(50)   NOT NULL                COMMENT '登录名，唯一',
    password    VARCHAR(128)  NOT NULL                COMMENT '密码（本项目为测试靶场，明文存储，便于观察数据）',
    phone       VARCHAR(20)   NULL                    COMMENT '手机号',
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';


-- ------------------------------------------------------------
-- 登录会话表（token -> 用户）
-- ------------------------------------------------------------
CREATE TABLE sessions (
    token       VARCHAR(64)  NOT NULL COMMENT '登录令牌',
    user_id     INT          NOT NULL COMMENT '所属用户',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (token),
    KEY idx_sessions_user (user_id),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录会话表';


-- ------------------------------------------------------------
-- 商品表
-- ------------------------------------------------------------
CREATE TABLE products (
    id          INT            NOT NULL AUTO_INCREMENT COMMENT '商品ID',
    name        VARCHAR(100)   NOT NULL                COMMENT '商品名称',
    category    VARCHAR(30)    NOT NULL                COMMENT '分类',
    price       DECIMAL(10,2)  NOT NULL                COMMENT '单价（元）',
    stock       INT            NOT NULL DEFAULT 0      COMMENT '库存',
    status      VARCHAR(20)    NOT NULL DEFAULT 'ON_SALE' COMMENT '状态：ON_SALE 在售 / OFF_SALE 下架',
    description VARCHAR(500)   NULL                    COMMENT '商品描述',
    created_at  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_products_category (category),
    KEY idx_products_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品表';


-- ------------------------------------------------------------
-- 购物车表
--   同一用户 + 同一商品只有一行，重复加购累加数量
-- ------------------------------------------------------------
CREATE TABLE carts (
    id          INT       NOT NULL AUTO_INCREMENT COMMENT '购物车行ID',
    user_id     INT       NOT NULL                COMMENT '所属用户',
    product_id  INT       NOT NULL                COMMENT '商品ID',
    quantity    INT       NOT NULL                COMMENT '数量',
    created_at  DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_carts_user_product (user_id, product_id),
    CONSTRAINT fk_carts_user    FOREIGN KEY (user_id)    REFERENCES users (id),
    CONSTRAINT fk_carts_product FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='购物车表';


-- ------------------------------------------------------------
-- 订单表
--   状态机：PENDING（待支付） -> PAID（已支付）
--                            -> CANCELLED（已取消）
-- ------------------------------------------------------------
CREATE TABLE orders (
    id          INT            NOT NULL AUTO_INCREMENT COMMENT '订单ID',
    user_id     INT            NOT NULL                COMMENT '下单用户',
    amount      DECIMAL(10,2)  NOT NULL                COMMENT '订单总金额（元）',
    status      VARCHAR(20)    NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING / PAID / CANCELLED',
    pay_type    VARCHAR(20)    NULL                    COMMENT '支付方式：ALIPAY / WECHAT',
    created_at  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '下单时间',
    paid_at     DATETIME       NULL                    COMMENT '支付时间',
    PRIMARY KEY (id),
    KEY idx_orders_user (user_id),
    KEY idx_orders_status (status),
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表';


-- ------------------------------------------------------------
-- 订单明细表（下单时把商品名与单价快照进来）
-- ------------------------------------------------------------
CREATE TABLE order_items (
    id            INT            NOT NULL AUTO_INCREMENT,
    order_id      INT            NOT NULL COMMENT '所属订单',
    product_id    INT            NOT NULL COMMENT '商品ID',
    product_name  VARCHAR(100)   NOT NULL COMMENT '下单时的商品名（快照）',
    price         DECIMAL(10,2)  NOT NULL COMMENT '下单时的单价（快照）',
    quantity      INT            NOT NULL COMMENT '数量',
    PRIMARY KEY (id),
    KEY idx_items_order (order_id),
    CONSTRAINT fk_items_order FOREIGN KEY (order_id) REFERENCES orders (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单明细表';


-- ------------------------------------------------------------
-- 库存流水表
--   每一次库存变动都留痕，测试时可用来做「数据一致性」反向核对：
--   期末库存 应等于 期初库存 + 所有流水的和
-- ------------------------------------------------------------
CREATE TABLE stock_logs (
    id          INT          NOT NULL AUTO_INCREMENT,
    product_id  INT          NOT NULL COMMENT '商品ID',
    change_qty  INT          NOT NULL COMMENT '变动量：正数入库，负数出库',
    reason      VARCHAR(30)  NOT NULL COMMENT '原因：ORDER_CREATE / ORDER_CANCEL',
    order_id    INT          NULL     COMMENT '关联订单',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_logs_product (product_id),
    CONSTRAINT fk_logs_product FOREIGN KEY (product_id) REFERENCES products (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='库存流水表';
