import { api } from './client'

/**
 * 管理后台专用 API 客户端 — 复用主 API 客户端（client.ts）的同一 axios 实例与拦截器。
 *
 * 板块E（冗余统一）：此前本文件与 client.ts 各自 create 了一份配置完全相同的 axios
 * 实例与 401 拦截器，属重复代码。现统一为同一实例，adminApi 仅为语义别名，
 * 消费方（admin 页面与 api/* 封装模块）无需改动。
 */
export const adminApi = api
